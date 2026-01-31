package main

import (
	"context"
	"fmt"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	_ "github.com/mattn/go-sqlite3"
	qrcodeTerminal "github.com/mdp/qrterminal/v3"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
)

// getAlternativePhone returns the alternative phone format for Brazilian numbers
func getAlternativePhone(originalPhone string) string {
	// Remove the 9 after the area code for Brazilian numbers if present
	if len(originalPhone) >= 13 && originalPhone[:3] == "+55" && originalPhone[5] == '9' {
		return originalPhone[:5] + originalPhone[6:]
	}
	return originalPhone
}

var client *whatsmeow.Client

// Helper to ensure we are connected before any operation
func ensureConnected(c *gin.Context) bool {
	if client == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "WhatsApp client not initialized"})
		return false
	}
	if !client.IsConnected() {
		fmt.Println("Reconnecting...")
		err := client.Connect()
		if err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "WhatsApp disconnected and failed to reconnect: " + err.Error()})
			return false
		}
	}
	return true
}

func main() {
	// 1. Setup Database with Context
	dbLog := waLog.Stdout("Database", "INFO", true)
	// Added context.Background() here
	store, err := sqlstore.New(context.Background(), "sqlite3", "file:whatsapp_store.db?_foreign_keys=on", dbLog)
	if err != nil {
		panic(err)
	}

	// Added context.Background() here
	device, err := store.GetFirstDevice(context.Background())
	if err != nil {
		panic(err)
	}

	clientLog := waLog.Stdout("Client", "INFO", true)
	client = whatsmeow.NewClient(device, clientLog)

	// 2. Event handler for stability
	client.AddEventHandler(func(evt interface{}) {
		switch v := evt.(type) {
		case *events.Disconnected:
			fmt.Println("Disconnected! Attempting auto-reconnect...")
		case *events.LoggedOut:
			fmt.Println("Session expired. Please scan QR code again.")
		default:
			_ = v
		}
	})

	// 3. QR Login Logic
	if client.Store.ID == nil {
		qrChan, _ := client.GetQRChannel(context.Background())
		err = client.Connect()
		if err != nil {
			panic(err)
		}
		for evt := range qrChan {
			if evt.Event == "code" {
				fmt.Println("Scan the QR Code:")
				qrcodeTerminal.GenerateHalfBlock(evt.Code, qrcodeTerminal.L, os.Stdout)
			}
		}
	} else {
		err = client.Connect()
		if err != nil {
			fmt.Printf("Initial connection failed: %v. Will try again on request.\n", err)
		}
	}

	router := gin.Default()

	// --- ENDPOINT: SEND OTP ---
	router.POST("/send_otp", func(c *gin.Context) {
		if !ensureConnected(c) {
			return
		}

		var body struct {
			Phone string `json:"phone"`
			Code  string `json:"code"`
		}
		if err := c.BindJSON(&body); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
			return
		}

		// Try sending to both with and without the leading 9 after area code for Brazilian numbers
		originalPhone := body.Phone
		alternativePhone := originalPhone
		// Only attempt for Brazilian numbers (country code 55) and if number has 13 digits (country+area+9+8)
		if len(originalPhone) == 13 && originalPhone[:3] == "+55" && originalPhone[5] == '9' {
			// Remove the 9 after the area code
			alternativePhone = originalPhone[:5] + originalPhone[6:]
		}

		msgText := fmt.Sprintf(`Seu código de acesso ao Cenourinhas é %s. Ele expira em 5 minutos.

Aline e Hugo ficam muito felizes com seu interesse. Curta bastante nosso site. Ele foi feito com muito carinho!
		`, body.Code)

		// Try original number first
		jid := types.NewJID(originalPhone, "s.whatsapp.net")
		_, err := client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &msgText,
		})
		if err != nil && alternativePhone != originalPhone {
			// Try alternative number if original failed
			jidAlt := types.NewJID(alternativePhone, "s.whatsapp.net")
			_, errAlt := client.SendMessage(context.Background(), jidAlt, &proto.Message{
				Conversation: &msgText,
			})
			if errAlt != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed for both formats: " + err.Error() + ", " + errAlt.Error()})
				return
			}
			c.JSON(http.StatusOK, gin.H{"status": "sent (alternative format)"})
			return
		} else if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "sent"})
	})

	// --- ENDPOINT: SEND MESSAGE (TEXT + IMAGE) ---
	router.POST("/send_message", func(c *gin.Context) {
		if !ensureConnected(c) {
			return
		}

		var phone, message string
		var imageData []byte
		var hasImage bool

		ct := c.ContentType()
		if ct == "application/json" {
			var body struct {
				Phone   string `json:"phone"`
				Message string `json:"message"`
				Image   []byte `json:"image"`
			}
			if err := c.BindJSON(&body); err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
				return
			}
			phone = body.Phone
			message = body.Message
			if len(body.Image) > 0 {
				imageData = body.Image
				hasImage = true
			}
		} else {
			phone = c.PostForm("phone")
			message = c.PostForm("message")
			file, err := c.FormFile("image")
			if err == nil {
				opened, _ := file.Open()
				defer opened.Close()
				imageData = make([]byte, file.Size)
				_, _ = opened.Read(imageData)
				hasImage = true
			}
		}

		// Try sending to both with and without the leading 9 after area code for Brazilian numbers
		originalPhone := phone
		alternativePhone := originalPhone
		if len(originalPhone) == 13 && originalPhone[:3] == "+55" && originalPhone[5] == '9' {
			alternativePhone = originalPhone[:5] + originalPhone[6:]
		}

		sendWithImage := func(jid types.JID) error {
			uploaded, err := client.Upload(context.Background(), imageData, whatsmeow.MediaImage)
			if err != nil {
				return fmt.Errorf("Upload failed: %w", err)
			}
			mimetype := http.DetectContentType(imageData)
			msg := &proto.Message{
				ImageMessage: &proto.ImageMessage{
					Caption:       &message,
					URL:           &uploaded.URL,
					Mimetype:      &mimetype,
					FileSHA256:    uploaded.FileSHA256,
					FileEncSHA256: uploaded.FileEncSHA256,
					MediaKey:      uploaded.MediaKey,
					FileLength:    &uploaded.FileLength,
					DirectPath:    &uploaded.DirectPath,
				},
			}
			_, err = client.SendMessage(context.Background(), jid, msg)
			return err
		}

		sendWithText := func(jid types.JID) error {
			_, err := client.SendMessage(context.Background(), jid, &proto.Message{
				Conversation: &message,
			})
			return err
		}

		// Try original number first
		jid := types.NewJID(originalPhone, "s.whatsapp.net")
		var err error
		if hasImage {
			err = sendWithImage(jid)
		} else {
			err = sendWithText(jid)
		}
		if err != nil && alternativePhone != originalPhone {
			// Try alternative number if original failed
			jidAlt := types.NewJID(alternativePhone, "s.whatsapp.net")
			if hasImage {
				errAlt := sendWithImage(jidAlt)
				if errAlt != nil {
					c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed for both formats: " + err.Error() + ", " + errAlt.Error()})
					return
				}
				c.JSON(http.StatusOK, gin.H{"status": "sent with image (alternative format)"})
				return
			} else {
				errAlt := sendWithText(jidAlt)
				if errAlt != nil {
					c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed for both formats: " + err.Error() + ", " + errAlt.Error()})
					return
				}
				c.JSON(http.StatusOK, gin.H{"status": "sent (alternative format)"})
				return
			}
		} else if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		if hasImage {
			c.JSON(http.StatusOK, gin.H{"status": "sent with image"})
		} else {
			c.JSON(http.StatusOK, gin.H{"status": "sent"})
		}
	})

	fmt.Println("Servidor WhatsApp rodando em http://localhost:8081")
	router.Run(":8081")
}
