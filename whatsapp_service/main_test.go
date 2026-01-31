package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestEnsureConnected(t *testing.T) {
	recorder := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(recorder)

	client = nil
	ok := ensureConnected(c)
	if ok {
		t.Error("expected ensureConnected to return false when client is nil")
	}
	if recorder.Code != http.StatusInternalServerError {
		t.Errorf("expected status 500, got %d", recorder.Code)
	}
}

func TestSendOtpHandler_BadJSON(t *testing.T) {
	recorder := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(recorder)
	c.Request = httptest.NewRequest("POST", "/send_otp", bytes.NewBuffer([]byte("bad json")))
	c.Request.Header.Set("Content-Type", "application/json")

	var body struct {
		Phone string `json:"phone"`
		Code  string `json:"code"`
	}
	err := c.BindJSON(&body)
	if err == nil {
		t.Error("expected BindJSON to fail on bad JSON")
	}
}

func TestSendMessageHandler_BadJSON(t *testing.T) {
	recorder := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(recorder)
	c.Request = httptest.NewRequest("POST", "/send_message", bytes.NewBuffer([]byte("bad json")))
	c.Request.Header.Set("Content-Type", "application/json")

	var body struct {
		Phone   string `json:"phone"`
		Message string `json:"message"`
		Image   []byte `json:"image"`
	}
	err := c.BindJSON(&body)
	if err == nil {
		t.Error("expected BindJSON to fail on bad JSON")
	}
}

func TestGetAlternativePhone_Examples(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{"+5531998765432", "+553198765432"},
		{"+553188765432", "+553188765432"},
		{"+14155552671", "+14155552671"},
		{"+5512345678", "+5512345678"},
	}
	for _, c := range cases {
		got := getAlternativePhone(c.in)
		if got != c.want {
			t.Errorf("getAlternativePhone(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestOtpMessageContent(t *testing.T) {
	code := "12345"
	msgText := buildOtpMessage(code)
	if code == "" || !bytes.Contains([]byte(msgText), []byte(code)) {
		t.Error("OTP code not found in message")
	}
	if !bytes.Contains([]byte(msgText), []byte("Cenourinhas")) {
		t.Error("Expected project name in OTP message")
	}
	if !bytes.Contains([]byte(msgText), []byte("5 minutos")) {
		t.Error("Expected expiration info in OTP message")
	}
}

func buildOtpMessage(code string) string {
	return "Aline e Hugo ficam muito felizes com seu interesse.\n\n\tSeu código de acesso ao Cenourinhas é " + code + ". Ele expira em 5 minutos.\n\n\tCurta bastante nosso site. Ele foi feito com muito carinho!\n\t"
}

func TestAlternativePhoneFormat(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "With leading 9 after area code",
			input:    "+5531998765432",
			expected: "+553198765432",
		},
		{
			name:     "No leading 9 after area code",
			input:    "+553188765432",
			expected: "+553188765432",
		},
		{
			name:     "Not Brazilian number",
			input:    "+14155552671",
			expected: "+14155552671",
		},
		{
			name:     "Short number",
			input:    "+5512345678",
			expected: "+5512345678",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			alt := getAlternativePhone(tt.input)
			if alt != tt.expected {
				t.Errorf("got %s, want %s", alt, tt.expected)
			}
		})
	}
}
