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

	fmt.Println("Servidor WhatsApp OTP rodando em http://localhost:8081")
	router.Run(":8081")
}
