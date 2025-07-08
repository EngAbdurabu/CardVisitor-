from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(14))
    photo = db.Column(db.String(100))  # صورة شخصية (اختيارية)
    qr_photo = db.Column(db.String(100))  # صورة QR
    qr_token = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed = db.Column(db.Boolean, default=False)
    attended = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6))  # رمز من 6 أرقام
    otp_created_at = db.Column(db.DateTime)  # وقت إنشاء الرمز
