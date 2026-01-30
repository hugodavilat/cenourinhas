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

		jid := types.NewJID(body.Phone, "s.whatsapp.net")
		msgText := fmt.Sprintf(`Aline e Hugo ficam muito felizes com seu interesse.
		
		Seu código de acesso ao Cenourinhas é %s. Ele expira em 5 minutos.
		
		Curta bastante nosso site. Ele foi feito com muito carinho!

		Se vc for um programador, nos ajude a melhorar ele contribuindo no GitHub: https://github.com/hugodavilat/cenourinhas
		`, body.Code)

		_, err := client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &msgText,
		})

		if err != nil {
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

		jid := types.NewJID(phone, "s.whatsapp.net")

		if hasImage {
			uploaded, err := client.Upload(context.Background(), imageData, whatsmeow.MediaImage)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "Upload failed: " + err.Error()})
				return
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
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, gin.H{"status": "sent with image"})
		} else {
			_, err := client.SendMessage(context.Background(), jid, &proto.Message{
				Conversation: &message,
			})
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, gin.H{"status": "sent"})
		}
	})

	fmt.Println("Servidor WhatsApp rodando em http://localhost:8081")
	router.Run(":8081")
}
