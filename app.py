import os
from flask import Flask
from flask_session import Session
from dotenv import load_dotenv

load_dotenv()

# Google OAuth 로컬 개발용 설정
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # HTTP 허용 (개발 환경 전용)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

# 서버사이드 세션 (쿠키 4KB 제한 우회)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.path.dirname(__file__), "flask_session")
app.config["SESSION_PERMANENT"] = False
Session(app)

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
