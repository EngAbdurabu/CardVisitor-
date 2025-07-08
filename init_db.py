from models import Visitor, db

# إنشاء كل الجداول
db.create_all()
print("✅ تم إنشاء قاعدة البيانات بنجاح.")
