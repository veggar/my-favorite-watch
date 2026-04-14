import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# Google OAuth 로컬 개발용 설정
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # HTTP 허용 (개발 환경 전용)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

# 블루프린트 등록
from routes.auth import auth_bp
from routes.sheet import sheet_bp
from routes.main import main_bp
from routes.item import item_bp
from routes.settings import settings_bp

app.register_blueprint(auth_bp)
app.register_blueprint(sheet_bp)
app.register_blueprint(main_bp)
app.register_blueprint(item_bp)
app.register_blueprint(settings_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=os.environ.get("FLASK_ENV") == "development")
