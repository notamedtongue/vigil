from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_caching import Cache
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import sqlite3
import os
import tweepy
from urllib.parse import urljoin, quote
from newspaper import Article
import re
import feedparser
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a secure key
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
socketio = SocketIO(app, async_mode='threading')

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('vigil.db')
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return User(user[0], user[1]) if user else None

# Database setup
def init_db():
    conn = sqlite3.connect('vigil.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS preferences 
                 (user_id INTEGER, bg_color TEXT, layout TEXT, FOREIGN KEY(user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()

# News sources (full list as provided)
news_sources = [
    "http://www.alt-market.us/",
    "http://antiwar.com/",
    "https://bitcoinmagazine.com/",
    "https://bombthrower.com/",
    "https://www.bullionstar.us/",
    "http://www.capitalistexploits.at/",
    "https://www.christophe-barraud.com/en/blog",
    "https://www.dollarcollapse.com/",
    "http://www.doctorhousingbubble.com/",
    "http://www.thefinancialrevolutionist.com/",
    "http://forexlive.com/",
    "http://gainspainscapital.com/",
    "https://gefira.org/",
    "https://www.gmgresearch.com/",
    "http://www.goldcore.com/",
    "http://implode-explode.com/",
    "http://www.insiderpaper.com/",
    "http://libertyblitzkrieg.com/",
    "http://maxkeiser.com/",
    "http://mises.org/",
    "https://mishtalk.com/",
    "https://newsquawk.com/",
    "http://www.oftwominds.com/blog.html",
    "http://oilprice.com/",
    "https://www.openthebooks.com/",
    "http://schiffgold.com/news/",
    "https://portfolioarmor.com/",
    "http://quoththeraven.substack.com/",
    "https://safehaven.com/",
    "http://slopeofhope.com/",
    "https://spotgamma.com/",
    "http://www.tfmetalsreport.com/",
    "https://www.theautomaticearth.com/",
    "http://www.theburningplatform.com/",
    "http://www.economicpopulist.org/",
    "https://libertarianinstitute.org/",
    "http://www.themistrading.com/",
    "https://thoughtfulmoney.com/",
    "http://www.valuewalk.com/",
    "http://wolfstreet.com/",
    "https://brownstone.org/",
    "https://www.africanews.com/",
    "https://www.arabnews.com/",
    "https://www.bild.de/politik/international/bild-international/home-44225950.bild.html",
    "http://en.people.cn/",
    "https://www.zeit.de/english/index",
    "https://www.economist.com/",
    "https://www.elmundo.es/",
    "https://www.hindustantimes.com/",
    "http://www.ft.com/",
    "https://www.haaretz.com/",
    "https://wyborcza.pl/0,0.html",
    "https://www.japantimes.co.jp/",
    "http://www.jpost.com/",
    "https://www.repubblica.it/",
    "https://www.lemonde.fr/en/",
    "https://www.themoscowtimes.com/",
    "https://www.theneweuropean.co.uk/",
    "https://asia.nikkei.com/",
    "https://www.smh.com.au/",
    "https://timesofindia.indiatimes.com/us",
    "https://www.theyeshivaworld.com/",
    "https://www.drudgereport.com/wx.htm",
    "http://www.mcclatchydc.com/",
    "http://www.pravdareport.com/world/",
    "http://www.interfax.com/news.asp",
    "http://www.ptinews.com/",
    "http://www.reuters.com/news/archive/politicsNews?date=today",
    "https://e.nyse.com/mac-desk-weekly-recap",
    "https://www.nyse.com/quote/index/NY.I",
    "https://www.investopedia.com/"
]

# Async news fetching
async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            return await response.text(), response.url
    except Exception as e:
        return None, f"Error fetching {url}: {e}"

def get_rss_feed_url(soup):
    link = soup.find('link', rel='alternate', type='application/rss+xml')
    return link['href'] if link and 'href' in link.attrs else None

def parse_rss_feed(rss_url, source_name):
    feed = feedparser.parse(rss_url)
    return [{"title": entry.title, "source": source_name, "url": entry.link} for entry in feed.entries[:5]]

def scrape_headlines(soup, source_name, base_url):
    items = []
    for tag in ['h1', 'h2', 'h3']:
        for headline in soup.find_all(tag):
            a = headline.find('a')
            if a and 'href' in a.attrs:
                title = a.text.strip()
                url = urljoin(str(base_url), a['href'])
                items.append({"title": title, "source": source_name, "url": url})
                if len(items) >= 5:
                    break
        if len(items) >= 5:
            break
    return items

async def fetch_news_from_source(session, url):
    html, base_url = await fetch_url(session, url)
    if not html:
        return [{"title": str(base_url), "source": url.split('//')[1].split('/')[0], "url": ""}]
    soup = BeautifulSoup(html, "html.parser")
    source_name = soup.title.string if soup.title else url.split('//')[1].split('/')[0]
    rss_url = get_rss_feed_url(soup)
    if rss_url:
        rss_url = urljoin(str(base_url), rss_url)
        return parse_rss_feed(rss_url, source_name)
    return scrape_headlines(soup, source_name, base_url)

async def fetch_news_async():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_news_from_source(session, url) for url in news_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_news = []
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
        return all_news

@cache.cached(timeout=600)
def fetch_news():
    return asyncio.run(fetch_news_async())


# Background task for real-time updates
def background_task():
    while True:
        news = fetch_news()
        social = None # fetch_social()
        socketio.emit('update', {'news': news, 'social': social}, namespace='/vigil')
        socketio.sleep(300)  # Update every 5 minutes

socketio.start_background_task(background_task)

# Article extraction
def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text or "No content extracted"
    except Exception as e:
        return f"Error fetching article: {e}"

# Routes
@app.route('/')
@login_required
def home():
    conn = sqlite3.connect('vigil.db')
    c = conn.cursor()
    c.execute("SELECT bg_color, layout FROM preferences WHERE user_id = ?", (current_user.id,))
    prefs = c.fetchone()
    if not prefs:
        c.execute("INSERT INTO preferences (user_id, bg_color, layout) VALUES (?, '#f0f0f0', 'grid')", (current_user.id,))
        conn.commit()
        bg_color, layout = '#f0f0f0', 'grid'
    else:
        bg_color, layout = prefs
    conn.close()
    return render_template('index.html', bg_color=bg_color, layout=layout)

@app.route('/customize', methods=['POST'])
@login_required
def customize():
    bg_color = request.form.get('bg_color', '#f0f0f0')
    layout = request.form.get('layout', 'grid')
    conn = sqlite3.connect('vigil.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO preferences (user_id, bg_color, layout) VALUES (?, ?, ?)", 
              (current_user.id, bg_color, layout))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))

@app.route('/save')
@login_required
def save_article():
    title = request.args.get('title')
    url = request.args.get('url')
    if not title or not url:
        return "Missing title or URL", 400
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:100]
    user_dir = f"saved/{current_user.id}"
    os.makedirs(user_dir, exist_ok=True)
    file_path = f"{user_dir}/{safe_title}.txt"
    article_text = extract_article_text(url)
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(f"Title: {title}\nSource: {url}\n\n{article_text}")
    return send_file(file_path, as_attachment=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('vigil.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1]))
            return redirect(url_for('home'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('vigil.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                      (username, generate_password_hash(password)))
            conn.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already taken')
        conn.close()
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# WebSocket events
@socketio.on('connect', namespace='/vigil')
def handle_connect():
    news = fetch_news()
    social = None # fetch_social()
    emit('update', {'news': news, 'social': social})

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True)