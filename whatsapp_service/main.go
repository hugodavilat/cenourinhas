package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"

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

func extractDigits(value string) string {
	var sb strings.Builder
	for _, r := range value {
		if r >= '0' && r <= '9' {
			sb.WriteRune(r)
		}
	}
	return sb.String()
}

func normalizePhone(value string) string {
	digits := extractDigits(value)
	digits = strings.TrimPrefix(digits, "00")
	return digits
}

// getAlternativePhone returns the alternative phone format for Brazilian numbers
func getAlternativePhone(originalPhone string) string {
	phone := normalizePhone(originalPhone)
	if len(phone) == 13 && strings.HasPrefix(phone, "55") && phone[4] == '9' {
		return phone[:4] + phone[5:]
	}
	if len(phone) == 12 && strings.HasPrefix(phone, "55") {
		return phone[:4] + "9" + phone[4:]
	}
	return phone
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

// URL do seu servidor Django que processará a lógica da IA
// Pode ser sobrescrito pela variável de ambiente `DJANGO_WEBHOOK_URL`.
var DjangoWebhookURL = ""

// notifyDjango envia a mensagem recebida para o seu backend em Python, usando JID como identificador
func notifyDjango(jid string, message string) {
	log.Printf("[Django Link] Notificando Django sobre mensagem de %s: %s\n", jid, message)
	data := map[string]string{
		"jid":     jid,
		"message": message,
	}
	jsonData, _ := json.Marshal(data)

	resp, err := http.Post(DjangoWebhookURL, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		fmt.Printf("[Django Link] Erro ao contactar Django: %v\n", err)
		return
	}
	defer resp.Body.Close()
}

func main() {
	// Configure Django webhook URL from environment, default to IPv4 loopback
	if v := os.Getenv("DJANGO_WEBHOOK_URL"); v != "" {
		DjangoWebhookURL = v
	} else {
		DjangoWebhookURL = "http://127.0.0.1:8000/api/whatsapp/gemini"
	}
	log.Printf("[Django Link] Using webhook URL: %s\n", DjangoWebhookURL)

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

	// Setup Django webhook handling server
	// HANDLER DE EVENTOS: Adicionado o gatilho para o Django
	client.AddEventHandler(func(evt interface{}) {
		switch v := evt.(type) {
		case *events.Message:
			// Ignorar mensagens enviadas por nós mesmos ou de grupos
			if v.Info.IsFromMe || v.Info.IsGroup {
				return
			}
			// Extrai texto da mensagem
			msgText := ""
			if v.Message.GetConversation() != "" {
				msgText = v.Message.GetConversation()
			} else if v.Message.ExtendedTextMessage != nil {
				msgText = *v.Message.ExtendedTextMessage.Text
			}

			if msgText != "" {
				senderJID := v.Info.Sender.ToNonAD().String()
				fmt.Printf("Mensagem recebida de %s: %s. Notificando Django...\n", senderJID, msgText)
				go notifyDjango(senderJID, msgText)
			}

		case *events.Disconnected:
			fmt.Println("Disconnected! Attempting auto-reconnect...")
		}
	})

	router := gin.Default()

	// --- ENDPOINT: SEND MESSAGE TO JID ---
	router.POST("/send_jid_message", func(c *gin.Context) {
		if !ensureConnected(c) {
			return
		}

		var body struct {
			JID     string `json:"jid"`
			Message string `json:"message"`
		}
		if err := c.BindJSON(&body); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
			return
		}

		jid, err := types.ParseJID(body.JID)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JID"})
			return
		}

		_, err = client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &body.Message,
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		c.JSON(http.StatusOK, gin.H{"status": "sent"})
	})

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

		// Normalize the user-entered phone number and try both with and without the leading 9 after area code for Brazilian numbers
		originalPhone := normalizePhone(body.Phone)
		alternativePhone := getAlternativePhone(originalPhone)

		msgText := fmt.Sprintf(`Seu código de acesso ao Cenourinhas é %s. Ele expira em 5 minutos.

Eu sou a IA do casamento e estou aqui para ajudar no que for preciso! Qualquer dúvida só chamar aqui.
		`, body.Code)

		// Try original number first
		jid := types.NewJID(originalPhone, "s.whatsapp.net")
		_, err := client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &msgText,
		})
		if err != nil && alternativePhone != originalPhone {
			fmt.Printf("send_otp original failed for %s: %v\n", originalPhone, err)
			// Try alternative number if original failed
			jidAlt := types.NewJID(alternativePhone, "s.whatsapp.net")
			_, errAlt := client.SendMessage(context.Background(), jidAlt, &proto.Message{
				Conversation: &msgText,
			})
			if errAlt != nil {
				fmt.Printf("send_otp alternative failed for %s: %v\n", alternativePhone, errAlt)
				c.JSON(http.StatusInternalServerError, gin.H{
					"error":             "Failed for both formats",
					"original_phone":    originalPhone,
					"alternative_phone": alternativePhone,
					"original_error":    err.Error(),
					"alternative_error": errAlt.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, gin.H{"status": "sent (alternative format)"})
			return
		} else if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error(), "phone": originalPhone})
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
		var fileData []byte
		var hasFile bool
		var fileName string
		var mimeType string

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
				fileData = body.Image
				hasFile = true
				// Default para JSON
				mimeType = http.DetectContentType(fileData)
			}
		} else {
			phone = c.PostForm("phone")
			message = c.PostForm("message")
			file, err := c.FormFile("image")
			if err == nil {
				opened, err := file.Open()
				if err != nil {
					c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to open uploaded file"})
					return
				}
				defer opened.Close()
				fileData, err = io.ReadAll(opened)
				if err != nil {
					c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read uploaded file"})
					return
				}
				hasFile = true
				fileName = file.Filename
				mimeType = file.Header.Get("Content-Type")
				if mimeType == "" {
					mimeType = http.DetectContentType(fileData)
				}
			}
		}

		// Normalize the user-entered phone number and try both with and without the leading 9 after area code for Brazilian numbers
		originalPhone := normalizePhone(phone)
		alternativePhone := getAlternativePhone(originalPhone)
		fmt.Printf("send_message request phone=%q original=%q alternative=%q hasFile=%v\n", phone, originalPhone, alternativePhone, hasFile)

		sendWithFile := func(jid types.JID) error {
			// Determinar tipo de mídia e garantir mimetype correto
			var mediaType whatsmeow.MediaType

			// Verificar se é PDF pela extensão ou mimetype
			isPDF := mimeType == "application/pdf" || mimeType == "application/octet-stream"
			if fileName != "" {
				for i := len(fileName) - 1; i >= 0; i-- {
					if fileName[i] == '.' {
						ext := fileName[i+1:]
						if ext == "pdf" || ext == "PDF" {
							isPDF = true
							mimeType = "application/pdf"
						}
						break
					}
				}
			}

			if isPDF {
				mediaType = whatsmeow.MediaDocument
				mimeType = "application/pdf" // Garantir mimetype correto para PDF
			} else {
				mediaType = whatsmeow.MediaImage
				// Garantir que é imagem
				if mimeType != "image/jpeg" && mimeType != "image/png" && mimeType != "image/gif" {
					mimeType = http.DetectContentType(fileData)
				}
			}

			uploaded, err := client.Upload(context.Background(), fileData, mediaType)
			if err != nil {
				return fmt.Errorf("Upload failed: %w", err)
			}

			// Criar mensagem baseada no tipo de mídia
			if isPDF {
				// Para PDF, usar DocumentMessage com todos os campos necessários
				msg := &proto.Message{
					DocumentMessage: &proto.DocumentMessage{
						URL:           &uploaded.URL,
						Mimetype:      &mimeType,
						Title:         &fileName, // Nome do arquivo como título
						FileSHA256:    uploaded.FileSHA256,
						FileEncSHA256: uploaded.FileEncSHA256,
						MediaKey:      uploaded.MediaKey,
						FileLength:    &uploaded.FileLength,
						DirectPath:    &uploaded.DirectPath,
						Caption:       &message,
						FileName:      &fileName,
					},
				}
				_, err = client.SendMessage(context.Background(), jid, msg)
				return err
			} else {
				// Para imagens, usar ImageMessage
				msg := &proto.Message{
					ImageMessage: &proto.ImageMessage{
						Caption:       &message,
						URL:           &uploaded.URL,
						Mimetype:      &mimeType,
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
		if hasFile {
			err = sendWithFile(jid)
		} else {
			err = sendWithText(jid)
		}
		if err != nil && alternativePhone != originalPhone {
			fmt.Printf("send_message original failed for %s: %v\n", originalPhone, err)
			// Try alternative number if original failed
			jidAlt := types.NewJID(alternativePhone, "s.whatsapp.net")
			if hasFile {
				errAlt := sendWithFile(jidAlt)
				if errAlt != nil {
					fmt.Printf("send_message alternative failed for %s: %v\n", alternativePhone, errAlt)
					c.JSON(http.StatusInternalServerError, gin.H{
						"error":             "Failed for both formats",
						"original_phone":    originalPhone,
						"alternative_phone": alternativePhone,
						"original_error":    err.Error(),
						"alternative_error": errAlt.Error(),
					})
					return
				}
				c.JSON(http.StatusOK, gin.H{"status": "sent with file (alternative format)"})
				return
			} else {
				errAlt := sendWithText(jidAlt)
				if errAlt != nil {
					fmt.Printf("send_message alternative failed for %s: %v\n", alternativePhone, errAlt)
					c.JSON(http.StatusInternalServerError, gin.H{
						"error":             "Failed for both formats",
						"original_phone":    originalPhone,
						"alternative_phone": alternativePhone,
						"original_error":    err.Error(),
						"alternative_error": errAlt.Error(),
					})
					return
				}
				c.JSON(http.StatusOK, gin.H{"status": "sent (alternative format)"})
				return
			}
		} else if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error(), "phone": originalPhone})
			return
		}
		if hasFile {
			fileType := "file"
			if fileName != "" && mimeType != "application/pdf" {
				fileType = "image"
			} else if mimeType == "application/pdf" {
				fileType = "PDF"
			}
			c.JSON(http.StatusOK, gin.H{"status": "sent with " + fileType})
		} else {
			c.JSON(http.StatusOK, gin.H{"status": "sent"})
		}
	})

	fmt.Println("Servidor WhatsApp rodando em http://localhost:8081")
	router.Run(":8081")
}
