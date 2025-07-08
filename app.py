from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    flash,
    session,
)
from models import Visitor, db
from flask_mail import Mail, Message
from weasyprint import HTML
import qrcode, secrets, os, random, re
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()
app = Flask(__name__)

# إعدادات عامة
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("database_uri")
app.config["UPLOAD_FOLDER"] = "static/uploads/"
app.config["SECRET_KEY"] = os.getenv("app_secret_key")

# إعدادات البريد الإلكتروني (غيّر هذه القيم للإنتاج)
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = os.getenv("port")
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("email_username")
app.config["MAIL_PASSWORD"] = os.getenv("email_passwrod")

# تهيئة الإضافات
db.init_app(app)
mail = Mail(app)

# إنشاء مجلد الرفع إن لم يكن موجودًا
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # استلام بيانات المستخدم
        full_name = request.form["full_name"]
        email = request.form["email"]
        phone = request.form["phone"]
        photo = request.files.get("photo")

        # التحقق من عدم تكرار البريد
        if Visitor.query.filter_by(email=email).first():
            flash("هذا البريد الإلكتروني مسجل مسبقًا.", "warning")
            return redirect(url_for("index"))

        # إنشاء رمز تحقق عشوائي
        otp = str(random.randint(100000, 999999))
        session["visitor_data"] = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "photo_filename": f"{datetime.now().timestamp()}_{photo.filename}",
            "otp_code": otp,
            "otp_created_at": datetime.utcnow().isoformat(),
        }

        # حفظ الصورة مؤقتًا
        photo_path = os.path.join(
            app.config["UPLOAD_FOLDER"], session["visitor_data"]["photo_filename"]
        )
        photo.save(photo_path)

        # إرسال رمز OTP بالبريد
        send_otp_email(full_name, email, otp)

        flash("تم إرسال رمز التحقق إلى بريدك الإلكتروني.", "info")
        return redirect(url_for("verify_otp"))

    return render_template("index.html")


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    visitor_data = session.get("visitor_data")
    if not visitor_data:
        flash("لا توجد بيانات تحقق محفوظة.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        entered_otp = request.form["otp"]
        otp_code = visitor_data["otp_code"]
        otp_created_at = datetime.fromisoformat(visitor_data["otp_created_at"])
        time_diff = datetime.utcnow() - otp_created_at

        # تحقق من صحة الرمز والمدة الزمنية
        if entered_otp == otp_code and time_diff.total_seconds() < 300:
            # إنشاء الزائر في قاعدة البيانات
            visitor = Visitor(
                full_name=visitor_data["full_name"],
                email=visitor_data["email"],
                phone=visitor_data["phone"],
                photo=visitor_data["photo_filename"],
                otp_code=otp_code,
                otp_created_at=otp_created_at,
                confirmed=True,
            )

            # إنشاء رمز QR
            token = secrets.token_urlsafe(16)
            visitor.qr_token = token
            db.session.add(visitor)
            db.session.commit()

            # توليد صورة QR وحفظها
            confirm_url = url_for("confirm_attendance", token=token, _external=True)
            qr_img = qrcode.make(confirm_url)
            qr_filename = f"qr_{visitor.id}.png"
            qr_path = os.path.join(app.config["UPLOAD_FOLDER"], qr_filename)
            qr_img.save(qr_path)
            visitor.qr_photo = qr_filename
            db.session.commit()

            # توليد ملف PDF
            pdf_path = generate_pdf(visitor, confirm_url)

            # إرسال بطاقة الحضور
            send_visitor_email(visitor, pdf_path)

            # حذف البيانات المؤقتة من session
            session.pop("visitor_data", None)

            flash("تم التحقق بنجاح وحُفظت بياناتك.", "success")
            return redirect(url_for("index"))
        else:
            flash("رمز غير صحيح أو منتهي", "danger")

    return render_template("verify_otp.html")


@app.route("/confirm_attendance/<token>")
def confirm_attendance(token):
    visitor = Visitor.query.filter_by(qr_token=token).first()
    if visitor:
        if visitor.attended:
            return "تم تسجيل الحضور مسبقًا."
        visitor.attended = True
        db.session.commit()
        return render_template("confirmed.html", visitor=visitor)
    return "رمز غير صالح", 404


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == os.getenv("admin_username") and request.form["password"] == os.getenv("admin_password"):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("بيانات الدخول غير صحيحة", "danger")
    return render_template("login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    visitors = Visitor.query.all()
    return render_template("admin_dashboard.html", visitors=visitors)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/scanner")
def scanner():
    return render_template("scanner.html")


@app.route('/delete_all', methods=['POST'])  # استخدم POST لأمان أكثر
def delete_all_data():
    try:
        # حذف كل البيانات من الجداول المطلوبة
        db.session.query(Visitor).delete()
        db.session.commit()
        flash('✅ تم حذف كل البيانات بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ حدث خطأ أثناء الحذف: {e}', 'danger')
        
    return redirect(url_for('index'))  # عد إلى الصفحة الرئيسية أو أي صفحة أخرى
    


def send_otp_email(full_name, email, otp_code):
    msg = Message("رمز التحقق OTP", sender="admin", recipients=[email])
    msg.body = f"مرحبًا {full_name}، رمز التحقق الخاص بك هو: {otp_code}"
    mail.send(msg)


def generate_pdf(visitor, confirm_url):
    pdf_filename = f"card_{visitor.id}.pdf"
    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], pdf_filename)

    image_url = url_for("static", filename=f"uploads/{visitor.photo}", _external=True)
    qr_url = url_for("static", filename=f"uploads/{visitor.qr_photo}", _external=True)

    html = render_template(
        "card_pdf.html",
        visitor=visitor,
        image_path=image_url,
        qr_path=qr_url,
        confirm_url=confirm_url,
    )
    HTML(
        string=html, base_url=url_for("static", filename="", _external=True)
    ).write_pdf(pdf_path)
    return pdf_path


def is_arabic(text):
    return bool(re.search(r"[\u0600-\u06FF]", text))


def send_visitor_email(visitor, pdf_path):
    confirm_url = url_for("confirm_attendance", token=visitor.qr_token, _external=True)
    msg = Message(
        "بطاقتك للحضور" if is_arabic(visitor.full_name) else "Your Attendance Card",
        sender="admin",
        recipients=[visitor.email],
    )
    msg.html = render_template(
        "card_pdf.html",
        visitor=visitor,
        confirm_url=confirm_url,
        is_arabic=is_arabic(visitor.full_name),
    )
    with app.open_resource(pdf_path) as pdf:
        msg.attach(f"card_{visitor.id}.pdf", "application/pdf", pdf.read())
    mail.send(msg)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
