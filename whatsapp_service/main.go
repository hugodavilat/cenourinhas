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
	waLog "go.mau.fi/whatsmeow/util/log"
)

func main() {
	// Create SQL store
	store, err := sqlstore.New(
		context.Background(),
		"sqlite3",
		"file:whatsapp_store.db?_foreign_keys=on",
		waLog.Noop,
	)
	if err != nil {
		panic(err)
	}

	// Load (or create) a WhatsApp device session
	device, err := store.GetFirstDevice(context.Background())
	if err != nil {
		panic(err)
	}

	fmt.Println("Starting WhatsApp client...")
	client := whatsmeow.NewClient(device, waLog.Noop)

	// QR Login
	if client.Store.ID == nil {
		fmt.Println("Nenhuma sessão encontrada. Gerando QR Code...")

		qrChan, _ := client.GetQRChannel(context.Background())

		go func() {
			for evt := range qrChan {
				if evt.Event == "code" {
					fmt.Println("Escaneie este QR Code para autenticar:")
					qrcodeTerminal.GenerateHalfBlock(evt.Code, qrcodeTerminal.L, os.Stdout)
					fmt.Println("------------")
				} else {
					fmt.Println("Evento:", evt.Event)
				}
			}
		}()
	}

	err = client.Connect()
	if err != nil {
		panic(err)
	}

	router := gin.Default()

	router.POST("/send_otp", func(c *gin.Context) {
		var body struct {
			Phone string `json:"phone"`
			Code  string `json:"code"`
		}

		if err := c.BindJSON(&body); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
			return
		}

		jid := types.NewJID(body.Phone, "s.whatsapp.net")

		msg := fmt.Sprintf("Seu código de acesso ao Cenourinhas é %s. Ele expira em 5 minutos.", body.Code)

		_, err := client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &msg,
		})

		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		c.JSON(http.StatusOK, gin.H{"status": "sent"})
	})

	// Novo endpoint: envio de mensagem customizada (texto e imagem)
	router.POST("/send_message", func(c *gin.Context) {
		var phone, message string
		var imageData []byte
		var hasImage bool

		// Detect content type
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
			if err == nil && file != nil {
				opened, err := file.Open()
				if err == nil {
					defer opened.Close()
					imageData = make([]byte, file.Size)
					_, err := opened.Read(imageData)
					if err == nil {
						hasImage = true
					}
				}
			}
		}

		jid := types.NewJID(phone, "s.whatsapp.net")

		if hasImage {
			uploaded, err := client.Upload(context.Background(), imageData, whatsmeow.MediaImage)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "Erro ao fazer upload da imagem: " + err.Error()})
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
			return
		}

		// Se não tem imagem, envia só texto
		_, err := client.SendMessage(context.Background(), jid, &proto.Message{
			Conversation: &message,
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "sent"})
	})

	fmt.Println("Servidor WhatsApp rodando em http://localhost:8081")
	router.Run(":8081")
}
