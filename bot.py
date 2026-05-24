import os
import json
import feedparser
import datetime
import google.generativeai as genai

# ==========================================
# 1. تنظیمات و سهمیه‌بندی قطعی (مجموعاً ۲۵ پست در روز)
# ==========================================
DAILY_QUOTAS = {
    "AI": 8,              # ۱. هوش مصنوعی (بیشترین)
    "Medical": 5,         # ۲. علوم پزشکی و سلامت
    "Tech": 5,            # ۳. دنیای تکنولوژی و گجت‌ها
    "Space": 3,           # ۴. نجوم و فضا
    "Science": 2,         # ۵. علوم پایه
    "CyberSecurity": 2    # ۶. هک و امنیت سایبری
}

# اولویت‌بندی آبشاری برای بررسی اخبار
PRIORITY_ORDER = ["AI", "Medical", "Tech", "Space", "Science", "CyberSecurity"]

RSS_SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://www.sciencedaily.com/rss/top/technology.xml",
    # سایر 13 منبع شما در اینجا قرار می‌گیرند...
]

# پیکربندی جمینای
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 2. مدیریت وضعیت روزانه (State Management)
# ==========================================
STATE_FILE = "daily_state.json"

def load_state():
    """خواندن وضعیت سهمیه‌های امروز. اگر روز جدید شده باشد، ریست می‌شود."""
    today = datetime.date.today().isoformat()
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            if state.get("date") == today:
                return state
            
    # ساختار اولیه برای روز جدید
    return {"date": today, "published_urls": [], "counts": {cat: 0 for cat in DAILY_QUOTAS}}

def save_state(state):
    """ذخیره وضعیت در فایل"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ==========================================
# 3. موتور هوش مصنوعی (جمینای)
# ==========================================
def categorize_news(title, summary):
    """
    قدم اول: فقط دسته‌بندی خبر برای جلوگیری از هدر رفتن توکن ترجمه
    خروجی باید دقیقاً یکی از کلیدهای DAILY_QUOTAS باشد یا None.
    """
    prompt = f"""
    Analyze the following news title and summary. 
    Categorize it strictly into ONE of the following categories:
    AI, Medical, Tech, Space, Science, CyberSecurity.
    If it doesn't fit well, output 'None'.
    Title: {title}
    Summary: {summary}
    Output ONLY the category name.
    """
    response = model.generate_content(prompt)
    category = response.text.strip()
    return category if category in DAILY_QUOTAS else None

def translate_and_format(title, content):
    """
    قدم دوم: ترجمه روان، خلاصه‌سازی و افزودن ایموجی و هشتگ
    """
    prompt = f"""
    متن زیر را به فارسی روان، جذاب و ژورنالیستی ترجمه و خلاصه کن.
    از لحن مناسب برای یک کانال تلگرامی/بله علمی استفاده کن.
    متن را با ایموجی‌های مرتبط تزئین کن و در انتها ۳ تا ۵ هشتگ مرتبط فارسی قرار بده.
    عنوان خبر: {title}
    متن خبر: {content}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

# ==========================================
# 4. انتشار در پیام‌رسان (بله / روبیکا)
# ==========================================
def send_to_channel(text):
    """ارسال متن نهایی به API پیام‌رسان"""
    # TODO: پیاده‌سازی درخواست POST به API بله یا روبیکا
    # url = "https://tapi.bale.ai/bot{TOKEN}/sendMessage"
    print(f"--- POSTING TO CHANNEL ---\n{text}\n--------------------------")
    return True

# ==========================================
# 5. منطق اصلی و آبشاری برنامه
# ==========================================
def main():
    state = load_state()
    
    # گرفتن تمام اخبار جدید از منابع
    all_articles = []
    for url in RSS_SOURCES:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]: # بررسی ۵ خبر اول هر فید
            if entry.link not in state["published_urls"]:
                all_articles.append(entry)
                
    if not all_articles:
        print("هیچ خبر جدیدی یافت نشد.")
        return

    # سیستم آبشاری: تلاش برای پیدا کردن و انتشار *یک* خبر در این اجرای ۳۰ دقیقه‌ای
    # که در بالاترین اولویتِ دارای ظرفیتِ خالی قرار داشته باشد.
    
    published_in_this_run = False

    for article in all_articles:
        # ۱. دسته‌بندی خبر
        category = categorize_news(article.title, article.summary)
        
        if not category:
            continue
            
        # ۲. بررسی سهمیه دسته‌بندی
        if state["counts"][category] < DAILY_QUOTAS[category]:
            # ۳. پردازش نهایی و تولید محتوا
            final_post = translate_and_format(article.title, article.summary)
            
            # ۴. ارسال
            success = send_to_channel(final_post)
            
            if success:
                # ۵. به‌روزرسانی وضعیت
                state["counts"][category] += 1
                state["published_urls"].append(article.link)
                save_state(state)
                published_in_this_run = True
                print(f"پست جدید در دسته {category} منتشر شد. سهمیه باقی‌مانده: {DAILY_QUOTAS[category] - state['counts'][category]}")
                break # در هر اجرای ۳۰ دقیقه‌ای فقط یک پست منتشر می‌کنیم تا کانال اسپم نشود

    if not published_in_this_run:
        print("در این اجرا، خبری که با سهمیه‌های باقی‌مانده همخوانی داشته باشد یافت نشد.")

if __name__ == "__main__":
    main()
