import datetime as dt
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st


st.set_page_config(page_title="图书馆跨时空留言板", page_icon="📚", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "library.db"
LEGACY_MESSAGES = BASE_DIR / "messages_data.json"
LEGACY_USERS = BASE_DIR / "users_data.json"
LEGACY_NOTIFICATIONS = BASE_DIR / "notifications_data.json"
LEGACY_HOT = BASE_DIR / "hot_data.json"
ADMIN_ACCOUNT = "1419742865"

def now_text():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()
def fetch_json(url, timeout=8):
    request = Request(
        url,
        headers={"User-Agent": "LibraryHackathon/1.0"}
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def lookup_open_library(query):
    query = query.strip()
    if not query:
        return []

    clean_query = query.replace("-", "").replace(" ", "")

    if clean_query.isdigit():
        url = (
            "https://openlibrary.org/search.json"
            f"?isbn={quote(clean_query)}&limit=40"
        )
    else:
        url = (
            "https://openlibrary.org/search.json"
            f"?q={quote(query)}&language=chi&limit=40"
        )

    try:
        data = fetch_json(url)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return []

    results = []
    seen = set()

    for item in data.get("docs", []):
        isbn_list = item.get("isbn", [])

        isbn = next(
            (
                value.replace("-", "").replace(" ", "")
                for value in isbn_list
                if len(value.replace("-", "").replace(" ", "")) in (10, 13)
                and value.replace("-", "").replace(" ", "").isdigit()
            ),
            None,
        )

        if not isbn:
            # 部分中文书目没有 ISBN，但 Open Library 会提供稳定的作品 ID。
            work_key = str(item.get("key", "")).strip()
            if work_key:
                isbn = "OL:" + work_key.rstrip("/").rsplit("/", 1)[-1]
        if not isbn or isbn in seen:
            continue
        seen.add(isbn)

        authors = item.get("author_name", [])
        subjects = item.get("subject", [])

        results.append({
            "isbn": isbn,
            "name": item.get("title", "未知书名"),
            "author": "、".join(authors[:3]) or "未知作者",
            "theme": "、".join(subjects[:3]) or "未分类",
            "icon": "📚",
            "item_type": "book",
            "identifier_type": "Open Library ID" if isbn.startswith("OL:") else "ISBN",
        })

    return results


@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def lookup_google_books(query):
    query = query.strip()
    if not query:
        return []

    results = []
    seen = set()
    search_terms = [query, f"intitle:{query}", f"inauthor:{query}"]
    for search_term in search_terms:
        url = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q={quote(search_term)}&langRestrict=zh&maxResults=40&printType=books"
        )
        try:
            data = fetch_json(url)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            continue

        for item in data.get("items", []):
            info = item.get("volumeInfo", {})
            identifiers = info.get("industryIdentifiers", [])
            isbn = next(
                (
                    str(identifier.get("identifier", "")).replace("-", "").replace(" ", "")
                    for identifier in identifiers
                    if len(str(identifier.get("identifier", "")).replace("-", "").replace(" ", "")) in (10, 13)
                ),
                None,
            )
            if not isbn:
                volume_id = str(item.get("id", "")).strip()
                if volume_id:
                    isbn = "GB:" + volume_id
            if not isbn or isbn in seen:
                continue
            seen.add(isbn)
            results.append({
                "isbn": isbn,
                "name": info.get("title", "未知书名"),
                "author": "、".join(info.get("authors", [])[:3]) or "未知作者",
                "theme": "、".join(info.get("categories", [])[:3]) or "未分类",
                "icon": "📚",
                "item_type": "book",
                "identifier_type": "Google Books ID" if isbn.startswith("GB:") else "ISBN",
            })
    return results


def openalex_abstract(inverted_index):
    if not isinstance(inverted_index, dict):
        return ""
    words = []
    for word, positions in inverted_index.items():
        for position in positions if isinstance(positions, list) else []:
            words.append((int(position), str(word)))
    return " ".join(word for _, word in sorted(words))


@st.cache_data(ttl=900, max_entries=100, show_spinner=False)
def lookup_openalex_papers(query):
    query = query.strip()
    if not query:
        return []
    url = (
        "https://api.openalex.org/works"
        f"?search={quote(query)}&per-page=40&sort=relevance_score:desc"
    )
    try:
        data = fetch_json(url, timeout=20)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    results = []
    seen = set()
    for work in data.get("results", []):
        work_id = str(work.get("id", "")).strip()
        doi = str(work.get("doi", "")).strip()
        doi_key = doi.lower().replace("https://doi.org/", "") if doi else ""
        identifier = f"DOI:{doi_key}" if doi_key else f"OA:{work_id.rsplit('/', 1)[-1]}"
        if identifier in seen:
            continue
        title = str(work.get("title", "")).strip()
        if not title:
            continue
        seen.add(identifier)
        authors = []
        for authorship in work.get("authorships", [])[:5]:
            author_name = str(authorship.get("author", {}).get("display_name", "")).strip()
            if author_name:
                authors.append(author_name)
        concepts = [
            str(concept.get("display_name", "")).strip()
            for concept in work.get("concepts", [])[:5]
            if concept.get("display_name")
        ]
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        landing_url = str(location.get("landing_page_url") or "").strip()
        pdf_url = str((location.get("pdf_url") or "")).strip()
        external_url = landing_url or pdf_url or doi or f"https://openalex.org/{work_id.rsplit('/', 1)[-1]}"
        results.append({
            "isbn": identifier,
            "name": title,
            "author": "、".join(authors) or "未知作者",
            "theme": "、".join(concepts) or "学术论文",
            "icon": "📄",
            "item_type": "paper",
            "identifier_type": "DOI" if doi_key else "OpenAlex ID",
            "doi": doi_key,
            "abstract": openalex_abstract(work.get("abstract_inverted_index")),
            "source_url": external_url,
            "journal_name": str(source.get("display_name") or "").strip(),
            "published_at": str(work.get("publication_date") or work.get("publication_year") or ""),
            "citation_count": int(work.get("cited_by_count") or 0),
        })
    return results


def normalize_issn(value):
    compact = re.sub(r"[^0-9Xx]", "", str(value or ""))
    if len(compact) != 8 or not compact[:7].isdigit():
        return ""
    check_value = 10 if compact[-1].upper() == "X" else int(compact[-1]) if compact[-1].isdigit() else -1
    total = sum(int(digit) * weight for digit, weight in zip(compact[:7], range(8, 1, -1)))
    if (total + check_value) % 11:
        return ""
    return f"{compact[:4]}-{compact[4:].upper()}"


def crossref_journal_title(item):
    title = item.get("title", "")
    if isinstance(title, list):
        title = title[0] if title else ""
    return str(title).strip()


@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def lookup_crossref_journals(query):
    query = query.strip()
    if not query:
        return []
    query_issn = normalize_issn(query)
    if query_issn:
        url = f"https://api.crossref.org/journals/{quote(query_issn)}"
    else:
        url = (
            "https://api.crossref.org/journals"
            f"?query={quote(query)}&rows=100"
        )
    try:
        message = fetch_json(url, timeout=15).get("message", {})
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    items = [message] if query_issn and isinstance(message, dict) else message.get("items", [])
    query_key = re.sub(r"\W", "", query.lower())

    def relevance(item):
        title_key = re.sub(r"\W", "", crossref_journal_title(item).lower())
        if title_key == query_key:
            rank = 0
        elif title_key.startswith(query_key):
            rank = 1
        elif query_key in title_key:
            rank = 2
        else:
            rank = 3
        return rank, len(title_key)

    results = []
    seen = set()
    for item in sorted(items, key=relevance):
        issns = [normalize_issn(value) for value in item.get("ISSN", [])]
        issn = next((value for value in issns if value), "")
        title = crossref_journal_title(item)
        if not issn or not title or issn in seen:
            continue
        seen.add(issn)
        subjects = item.get("subject", [])
        results.append({
            "isbn": f"ISSN:{issn}",
            "name": title,
            "author": str(item.get("publisher", "")).strip() or "未知出版机构",
            "theme": "、".join(subjects[:3]) if isinstance(subjects, list) and subjects else "学术期刊",
            "icon": "📰",
            "item_type": "journal",
            "identifier_type": "ISSN",
        })
        if len(results) >= 30:
            break
    return results


@st.cache_data(ttl=1800, max_entries=100, show_spinner=False)
def lookup_crossref_journal_issues(journal_identifier):
    """获取 Crossref 收录的期刊期次，并按卷号、期号和出版日期归并。"""
    issn = normalize_issn(str(journal_identifier).replace("ISSN:", ""))
    if not issn:
        return []
    url = (
        f"https://api.crossref.org/journals/{quote(issn)}/works"
        "?filter=type:journal-article&rows=1000"
        "&select=title,volume,issue,published,container-title,URL"
        "&sort=published&order=desc"
    )
    try:
        items = fetch_json(url, timeout=20).get("message", {}).get("items", [])
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    grouped = {}
    for item in items:
        volume = str(item.get("volume", "")).strip()
        issue = str(item.get("issue", "")).strip()
        dates = item.get("published", {}).get("date-parts", [])
        date_parts = dates[0] if dates and isinstance(dates[0], list) else []
        year = str(date_parts[0]) if date_parts else ""
        month = str(date_parts[1]).zfill(2) if len(date_parts) > 1 else ""
        day = str(date_parts[2]).zfill(2) if len(date_parts) > 2 else ""
        published = "-".join(part for part in (year, month, day) if part)
        if not (volume or issue or published):
            continue
        key = "|".join((volume, issue, published[:7] if not issue else ""))
        if key in grouped:
            continue
        container_titles = item.get("container-title", [])
        journal_name = container_titles[0] if container_titles else "期刊"
        label_parts = []
        if volume:
            label_parts.append(f"卷 {volume}")
        if issue:
            label_parts.append(f"期 {issue}")
        if published:
            label_parts.append(published)
        label = " · ".join(label_parts) or "未知期次"
        issue_id = f"ISSUE:{issn}:{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"
        grouped[key] = {
            "isbn": issue_id,
            "name": f"{journal_name} · {label}",
            "author": "未知出版机构",
            "theme": f"{label}（Crossref 收录期次）",
            "icon": "📰",
            "item_type": "journal_issue",
            "identifier_type": "期次",
            "parent_isbn": f"ISSN:{issn}",
            "issue_label": label,
            "published_at": published,
            "url": str(item.get("URL", "")).strip(),
        }
    return list(grouped.values())


def wikidata_author_from_description(description):
    for pattern in (
        r"作者[：:为是]?\s*([^，。,；;]+)",
        r"([^，。,；;]+?)(?:创作|所著)的?(?:长篇|中篇|短篇)?小说",
        r"([^，。,；;\s]+?)(?:所)?著(?:作)?$",
        r"\bby\s+([^,.;]+)$",
    ):
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            author = match.group(1).strip()
            if author and not re.search(r"\d|年", author):
                return author
    return "未知作者"


@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def lookup_wikidata(query):
    query = query.strip()
    if not query:
        return []
    language = "zh-hans" if contains_chinese(query) else "en"
    search_url = (
        "https://www.wikidata.org/w/api.php"
        "?action=wbsearchentities"
        f"&search={quote(query)}&language={language}&uselang={language}"
        "&type=item&limit=30&format=json"
    )
    try:
        search_data = fetch_json(search_url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    results = []
    book_words = (
        "书籍", "書籍", "图书", "圖書", "小说", "小說", "文学作品",
        "文學作品", "著作", "诗集", "詩集", "文集", "散文", "童话",
        "童話", "剧本", "劇本", "book", "novel", "literary work",
    )
    journal_words = (
        "期刊", "学术杂志", "學術雜誌", "科学杂志", "科學雜誌",
        "journal", "academic magazine", "scientific magazine", "periodical",
    )
    seen_titles = set()
    for item in search_data.get("search", []):
        entity_id = str(item.get("id", "")).strip()
        title = str(item.get("label", "")).strip()
        description = str(item.get("description", "")).strip()
        if not entity_id.startswith("Q") or not title:
            continue
        description_lower = description.lower()
        is_journal = any(word in description_lower for word in journal_words)
        if not is_journal and not any(word in description_lower for word in book_words):
            continue
        title_key = re.sub(r"[^\w\u4e00-\u9fff]", "", title.lower())
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        results.append({
            "isbn": f"WD:{entity_id}",
            "name": title,
            "author": "未知出版机构" if is_journal else wikidata_author_from_description(description),
            "theme": description or "Wikidata 资料",
            "icon": "📰" if is_journal else "📚",
            "item_type": "journal" if is_journal else "book",
            "identifier_type": "Wikidata ID",
        })
    return results


def contains_chinese(value):
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def is_known_author(author):
    return str(author or "").strip().lower() not in {
        "", "未知作者", "未知出版机构", "unknown", "unknown author", "unknown publisher",
    }


@st.cache_data(ttl=604800, max_entries=500, show_spinner=False)
def lookup_wikidata_author(author):
    """使用 Wikidata 的人物别名自动取得简体中文常用名。"""
    author = str(author or "").strip()
    if not is_known_author(author):
        return "未知作者"
    url = (
        "https://www.wikidata.org/w/api.php"
        "?action=wbsearchentities"
        f"&search={quote(author)}&language=zh-hans&uselang=zh-hans"
        "&type=item&limit=5&format=json"
    )
    try:
        data = fetch_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return author
    person_words = (
        "作家", "作者", "诗人", "小说家", "文学家", "剧作家", "编剧",
        "writer", "author", "poet", "novelist", "playwright", "human",
    )
    for item in data.get("search", []):
        label = str(item.get("label", "")).strip()
        description = str(item.get("description", "")).lower()
        if label and any(word in description for word in person_words):
            return label
    return author


def canonical_author(author):
    parts = [
        part.strip()
        for part in re.split(r"[、,，;/；]+", str(author or ""))
        if part.strip()
    ]
    if not parts:
        return "未知作者"
    return "、".join(lookup_wikidata_author(part) for part in parts[:3])


def normalize_remote_results(results, query=""):
    """优先中文书名，并合并同一中文书名的重复目录。"""
    normalized = []
    for book in results:
        item = dict(book)
        item["author"] = str(item.get("author") or "未知作者").strip()
        item["name"] = str(item.get("name", "未知书名")).strip() or "未知书名"
        item["item_type"] = item.get("item_type", "book")
        item["identifier_type"] = item.get("identifier_type", "ISBN")
        normalized.append(item)

    # 同一搜索如果有中文标题，只保留中文标题，避免中英文版本同时出现。
    chinese_titles = [item for item in normalized if contains_chinese(item.get("name"))]
    if contains_chinese(query) and chinese_titles:
        normalized = chinese_titles

    grouped = {}
    for item in normalized:
        title_key = (
            item["item_type"],
            re.sub(r"[^\w\u4e00-\u9fff]", "", item["name"].lower()),
        )
        grouped.setdefault(title_key, []).append(item)

    authors_to_resolve = set()
    for same_title_books in grouped.values():
        group_authors = {
            item["author"] for item in same_title_books
            if is_known_author(item.get("author"))
        }
        author_keys = {
            re.sub(r"[^\w\u4e00-\u9fff]", "", author.lower())
            for author in group_authors
        }
        if len(author_keys) > 1:
            authors_to_resolve.update(group_authors)
    resolved_authors = {
        author: canonical_author(author)
        for author in sorted(authors_to_resolve)
    }

    unique = []
    for same_title_books in grouped.values():
        selected = dict(same_title_books[0])
        authors = [
            resolved_authors.get(item["author"], item["author"])
            for item in same_title_books
            if is_known_author(item.get("author"))
        ]
        if authors:
            preferred = next(
                (author for author in authors if contains_chinese(author)),
                authors[0],
            )
            selected["author"] = preferred
        unique.append(selected)

    query_key = re.sub(r"[^\w\u4e00-\u9fff]", "", query.lower())
    query_identifier = re.sub(r"[^0-9x]", "", query.lower())

    def relevance(item):
        title_key = re.sub(r"[^\w\u4e00-\u9fff]", "", item["name"].lower())
        identifier_key = re.sub(r"[^0-9x]", "", str(item.get("isbn", "")).lower())
        if query_identifier and len(query_identifier) >= 8 and query_identifier in identifier_key:
            rank = -1
        elif title_key == query_key:
            rank = 0
        elif query_key and title_key.startswith(query_key):
            rank = 1
        elif query_key and query_key in title_key:
            rank = 2
        else:
            rank = 3
        return rank, 0 if item.get("item_type") == "journal" else 1, len(title_key)

    return sorted(unique, key=relevance)[:60]


def admin_accounts_from_secrets():
    accounts = {}
    try:
        secrets = st.secrets
        admins = secrets.get("admins", {})
        if hasattr(admins, "items"):
            for account, config in admins.items():
                account = str(account).strip()
                if not account:
                    continue
                if hasattr(config, "get"):
                    password = config.get("password", config.get("admin_password", ""))
                    name = config.get("name", "管理员")
                else:
                    password, name = config, "管理员"
                if str(password).strip():
                    accounts[account] = {"password": str(password), "name": str(name).strip() or "管理员"}
        for key in ("admin_password", "ADMIN_PASSWORD"):
            if key in secrets and str(secrets[key]).strip():
                accounts.setdefault(ADMIN_ACCOUNT, {"password": str(secrets[key]), "name": "管理员"})
        legacy_admin = secrets.get("admin", {})
        if hasattr(legacy_admin, "get"):
            password = legacy_admin.get("password", legacy_admin.get("admin_password", ""))
            if str(password).strip():
                accounts.setdefault(ADMIN_ACCOUNT, {"password": str(password), "name": "管理员"})
    except Exception:
        pass
    return accounts


def is_reserved_admin_account(account):
    return account == ADMIN_ACCOUNT or account in admin_accounts_from_secrets()


def current_user():
    return st.session_state.get("user")


def is_admin():
    user = current_user()
    return bool(user and user.get("role") == "admin")


def can_delete(comment):
    user = current_user()
    return bool(user and (is_admin() or comment.get("user_account") == user.get("account")))


def read_json(path, default):
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def connect_db():
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_column(db, table, column, definition):
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                isbn TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                theme TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '📚',
                item_type TEXT NOT NULL DEFAULT 'book',
                identifier_type TEXT NOT NULL DEFAULT 'ISBN',
                parent_isbn TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                doi TEXT NOT NULL DEFAULT '',
                abstract TEXT NOT NULL DEFAULT '',
                journal_name TEXT NOT NULL DEFAULT '',
                citation_count INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                account TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                isbn TEXT NOT NULL REFERENCES books(isbn) ON DELETE RESTRICT,
                parent_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
                subject TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                name TEXT NOT NULL,
                user_account TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_comments_book_parent ON comments(isbn, parent_id);
            CREATE TABLE IF NOT EXISTS comment_likes (
                comment_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
                account TEXT NOT NULL,
                PRIMARY KEY(comment_id, account)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                account TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_account ON notifications(account, is_read);
            CREATE TABLE IF NOT EXISTS searches (
                query TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                last_used TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visits (
                visit_date TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS book_requests (
                id TEXT PRIMARY KEY,
                requested_by TEXT NOT NULL,
                book_id TEXT NOT NULL,
                name TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                theme TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '📚',
                item_type TEXT NOT NULL DEFAULT 'book',
                identifier_type TEXT NOT NULL DEFAULT 'ISBN',
                doi TEXT NOT NULL DEFAULT '',
                abstract TEXT NOT NULL DEFAULT '',
                journal_name TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                citation_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by TEXT,
                UNIQUE(requested_by, book_id)
            );
            CREATE INDEX IF NOT EXISTS idx_book_requests_status
            ON book_requests(status, created_at);
            """
        )
        ensure_column(db, "books", "item_type", "TEXT NOT NULL DEFAULT 'book'")
        ensure_column(db, "books", "identifier_type", "TEXT NOT NULL DEFAULT 'ISBN'")
        ensure_column(db, "books", "parent_isbn", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "published_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "source_url", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "doi", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "abstract", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "journal_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "books", "citation_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "book_requests", "item_type", "TEXT NOT NULL DEFAULT 'book'")
        ensure_column(db, "book_requests", "identifier_type", "TEXT NOT NULL DEFAULT 'ISBN'")
        ensure_column(db, "book_requests", "doi", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "book_requests", "abstract", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "book_requests", "journal_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "book_requests", "published_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "book_requests", "source_url", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "book_requests", "citation_count", "INTEGER NOT NULL DEFAULT 0")
        migrate_legacy_data(db)


def normalize_legacy_comment(comment, fallback_id):
    if not isinstance(comment, dict):
        return None
    return {
        "id": str(comment.get("id") or fallback_id),
        "subject": str(comment.get("subject", comment.get("message_title", ""))),
        "content": str(comment.get("content", "")).strip(),
        "name": str(comment.get("name", "匿名用户")),
        "user_account": str(comment.get("user_account", comment.get("account", ""))),
        "created_at": str(comment.get("date", comment.get("timestamp", now_text()))),
        "likes": [str(item) for item in comment.get("likes", [])] if isinstance(comment.get("likes", []), list) else [],
        "replies": comment.get("replies", []) if isinstance(comment.get("replies", []), list) else [],
    }


def migrate_comment(db, isbn, comment, parent_id=None, fallback_id=None):
    item = normalize_legacy_comment(comment, fallback_id or uuid.uuid4().hex)
    if not item or not item["content"]:
        return
    comment_id = item["id"]
    exists = db.execute("SELECT 1 FROM comments WHERE id=?", (comment_id,)).fetchone()
    if not exists:
        db.execute(
            "INSERT INTO comments(id,isbn,parent_id,subject,content,name,user_account,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (comment_id, isbn, parent_id, item["subject"], item["content"], item["name"], item["user_account"], item["created_at"]),
        )
        db.executemany(
            "INSERT OR IGNORE INTO comment_likes(comment_id,account) VALUES(?,?)",
            [(comment_id, account) for account in item["likes"] if account.strip()],
        )
    for index, reply in enumerate(item["replies"]):
        migrate_comment(db, isbn, reply, comment_id, f"{comment_id}-reply-{index}")


def migrate_legacy_data(db):
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        users = read_json(LEGACY_USERS, {})
        if isinstance(users, dict):
            for account, user in users.items():
                if isinstance(user, dict) and user.get("password"):
                    db.execute(
                        "INSERT OR IGNORE INTO users(account,name,password_hash,created_at) VALUES(?,?,?,?)",
                        (str(account), str(user.get("name", account)), str(user["password"]), now_text()),
                    )
    if db.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0:
        messages = read_json(LEGACY_MESSAGES, {})
        if isinstance(messages, dict):
            for isbn, entries in messages.items():
                if db.execute("SELECT 1 FROM books WHERE isbn=?", (str(isbn),)).fetchone() is None:
                    db.execute(
                        "INSERT INTO books(isbn,name,author,theme,icon,enabled,created_at) VALUES(?,?,?,?,?,1,?)",
                        (str(isbn), str(isbn), "", "", "📚", now_text()),
                    )
                for index, entry in enumerate(entries if isinstance(entries, list) else []):
                    migrate_comment(db, str(isbn), entry, None, f"legacy-{isbn}-{index}")
    if db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0:
        notifications = read_json(LEGACY_NOTIFICATIONS, {})
        if isinstance(notifications, dict):
            for account, items in notifications.items():
                for item in items if isinstance(items, list) else []:
                    if isinstance(item, dict):
                        db.execute(
                            "INSERT OR IGNORE INTO notifications(id,account,title,body,created_at,is_read) VALUES(?,?,?,?,?,?)",
                            (str(item.get("id", uuid.uuid4().hex)), str(account), str(item.get("title", "通知")), str(item.get("body", "")), str(item.get("date", now_text())), int(bool(item.get("read")))),
                        )
    hot = read_json(LEGACY_HOT, {})
    if isinstance(hot, dict) and db.execute("SELECT COUNT(*) FROM searches").fetchone()[0] == 0:
        for query in hot.get("hot_searches", []) if isinstance(hot.get("hot_searches", []), list) else []:
            db.execute("INSERT INTO searches(query,count,last_used) VALUES(?,?,?) ON CONFLICT(query) DO UPDATE SET count=count+1,last_used=excluded.last_used", (str(query), 1, now_text()))
        for visit_date, count in (hot.get("visit_stats", {}) or {}).items():
            db.execute("INSERT OR IGNORE INTO visits(visit_date,count) VALUES(?,?)", (str(visit_date), int(count)))


def books(include_disabled=False, include_issues=False):
    query = "SELECT * FROM books"
    if not include_disabled:
        query += " WHERE enabled=1"
    if not include_issues:
        query += " AND" if " WHERE " in query else " WHERE"
        query += " item_type != 'journal_issue'"
    query += " ORDER BY name COLLATE NOCASE"
    with connect_db() as db:
        return [dict(row) for row in db.execute(query)]


def popular_books(limit=6):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT b.*,
                   (SELECT COUNT(*)
                    FROM comments c
                    WHERE c.isbn=b.isbn AND c.parent_id IS NULL) AS comments_count,
                   (SELECT COUNT(*)
                    FROM comment_likes cl
                    JOIN comments c ON c.id=cl.comment_id
                    WHERE c.isbn=b.isbn) AS likes_count
            FROM books b
            WHERE b.enabled=1 AND b.item_type != 'journal_issue'
            ORDER BY comments_count DESC, likes_count DESC, b.name COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def item_type_label(item):
    if item.get("item_type") == "journal":
        return "期刊"
    if item.get("item_type") == "journal_issue":
        return "期次"
    if item.get("item_type") == "paper":
        return "论文"
    return "书籍"


def item_creator_label(item):
    return "出版机构" if item.get("item_type") in ("journal", "journal_issue") else "作者"


def open_catalog_item(item):
    if item.get("item_type") == "journal":
        st.session_state.current_journal = item
        st.session_state.page = "期刊期次"
        st.session_state.current_book = None
        st.rerun()
    open_book(item["isbn"])


def journal_issue_rows(parent_isbn):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM books
            WHERE enabled=1 AND item_type='journal_issue' AND parent_isbn=?
            ORDER BY published_at DESC, name COLLATE NOCASE
            """,
            (parent_isbn,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_journal_issues(journal, issues):
    with connect_db() as db:
        for issue in issues:
            db.execute(
                """
                INSERT INTO books(
                    isbn,name,author,theme,icon,item_type,identifier_type,
                    parent_isbn,published_at,source_url,enabled,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(isbn) DO UPDATE SET
                    name=excluded.name,author=excluded.author,theme=excluded.theme,
                    icon=excluded.icon,item_type=excluded.item_type,
                    identifier_type=excluded.identifier_type,
                    parent_isbn=excluded.parent_isbn,published_at=excluded.published_at,
                    source_url=excluded.source_url,enabled=1
                """,
                (
                    issue["isbn"], issue["name"], issue["author"], issue["theme"],
                    issue["icon"], issue.get("item_type", "journal_issue"),
                    issue.get("identifier_type", "期次"), issue.get("parent_isbn", journal["isbn"]),
                    issue.get("published_at", ""), issue.get("url", ""),
                    now_text(),
                ),
            )


def item_identifier(item):
    value = str(item.get("isbn", item.get("book_id", "")))
    if value.startswith(("ISSN:", "WD:", "DOI:", "OA:")):
        return value.split(":", 1)[1]
    return value


def item_identifier_text(item):
    if item.get("item_type") == "journal_issue":
        return f"期次标识：{item_identifier(item)}"
    identifier_type = item.get("identifier_type") or (
        "ISSN" if str(item.get("isbn", item.get("book_id", ""))).startswith("ISSN:") else "ISBN"
    )
    return f"{identifier_type}：{item_identifier(item)}"


def save_remote_book(book):
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO books(
                isbn,
                name,
                author,
                theme,
                icon,
                item_type,
                identifier_type,
                parent_isbn,
                published_at,
                source_url,
                doi,
                abstract,
                journal_name,
                citation_count,
                enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                name = excluded.name,
                author = excluded.author,
                theme = excluded.theme,
                icon = excluded.icon,
                item_type = excluded.item_type,
                identifier_type = excluded.identifier_type,
                parent_isbn = excluded.parent_isbn,
                published_at = excluded.published_at,
                source_url = excluded.source_url,
                doi = excluded.doi,
                abstract = excluded.abstract,
                journal_name = excluded.journal_name,
                citation_count = excluded.citation_count,
                enabled = 1
            """,
            (
                book["isbn"],
                book["name"],
                book["author"],
                book["theme"],
                book["icon"],
                book.get("item_type", "book"),
                book.get("identifier_type", "ISBN"),
                book.get("parent_isbn", ""),
                book.get("published_at", ""),
                book.get("source_url", ""),
                book.get("doi", ""),
                book.get("abstract", ""),
                book.get("journal_name", ""),
                int(book.get("citation_count", 0) or 0),
                now_text(),
            ),
        )


def book_request_status(book_id, account):
    if get_book(book_id):
        return "added"
    with connect_db() as db:
        row = db.execute(
            "SELECT status FROM book_requests WHERE requested_by=? AND book_id=?",
            (str(account), str(book_id)),
        ).fetchone()
    return row["status"] if row else None


def create_book_request(book, account):
    if get_book(book["isbn"]):
        return "added"
    request_id = uuid.uuid4().hex
    with connect_db() as db:
        existing = db.execute(
            "SELECT status FROM book_requests WHERE requested_by=? AND book_id=?",
            (str(account), str(book["isbn"])),
        ).fetchone()
        if existing and existing["status"] in ("pending", "approved"):
            return existing["status"]
        if existing:
            db.execute(
                """
                UPDATE book_requests
                SET name=?,author=?,theme=?,icon=?,item_type=?,identifier_type=?,
                    doi=?,abstract=?,journal_name=?,published_at=?,source_url=?,citation_count=?,
                    status='pending',created_at=?,
                    reviewed_at=NULL,reviewed_by=NULL
                WHERE requested_by=? AND book_id=?
                """,
                (
                    book["name"],
                    book["author"],
                    book["theme"],
                    book["icon"],
                    book.get("item_type", "book"),
                    book.get("identifier_type", "ISBN"),
                    book.get("doi", ""),
                    book.get("abstract", ""),
                    book.get("journal_name", ""),
                    book.get("published_at", ""),
                    book.get("source_url", ""),
                    int(book.get("citation_count", 0) or 0),
                    now_text(),
                    str(account),
                    str(book["isbn"]),
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO book_requests(
                    id,requested_by,book_id,name,author,theme,icon,item_type,
                    identifier_type,doi,abstract,journal_name,published_at,source_url,
                    citation_count,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)
                """,
                (
                    request_id,
                    str(account),
                    str(book["isbn"]),
                    book["name"],
                    book["author"],
                    book["theme"],
                    book["icon"],
                    book.get("item_type", "book"),
                    book.get("identifier_type", "ISBN"),
                    book.get("doi", ""),
                    book.get("abstract", ""),
                    book.get("journal_name", ""),
                    book.get("published_at", ""),
                    book.get("source_url", ""),
                    int(book.get("citation_count", 0) or 0),
                    now_text(),
                ),
            )
    return "pending"


def pending_book_requests():
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM book_requests
            WHERE status='pending'
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def pending_request_count():
    with connect_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM book_requests WHERE status='pending'"
        ).fetchone()[0]


def review_book_request(request_id, approved):
    reviewer = current_user()
    if not reviewer or not is_admin():
        return False
    with connect_db() as db:
        request_row = db.execute(
            "SELECT * FROM book_requests WHERE id=? AND status='pending'",
            (request_id,),
        ).fetchone()
    if not request_row:
        return False
    request_item = dict(request_row)
    if approved:
        save_remote_book({
            "isbn": request_item["book_id"],
            "name": request_item["name"],
            "author": request_item["author"],
            "theme": request_item["theme"],
            "icon": request_item["icon"],
            "item_type": request_item.get("item_type", "book"),
            "identifier_type": request_item.get("identifier_type", "ISBN"),
            "doi": request_item.get("doi", ""),
            "abstract": request_item.get("abstract", ""),
            "journal_name": request_item.get("journal_name", ""),
            "published_at": request_item.get("published_at", ""),
            "source_url": request_item.get("source_url", ""),
            "citation_count": request_item.get("citation_count", 0),
        })
        with connect_db() as db:
            accounts = {
                row[0]
                for row in db.execute(
                    "SELECT requested_by FROM book_requests WHERE book_id=? AND status='pending'",
                    (request_item["book_id"],),
                )
            }
            db.execute(
                """
                UPDATE book_requests
                SET status='approved',reviewed_at=?,reviewed_by=?
                WHERE book_id=? AND status='pending'
                """,
                (now_text(), reviewer["account"], request_item["book_id"]),
            )
        notify_users(
            accounts,
            "书刊添加申请已通过",
            f"《{request_item['name']}》已加入馆藏。",
        )
    else:
        with connect_db() as db:
            db.execute(
                """
                UPDATE book_requests
                SET status='rejected',reviewed_at=?,reviewed_by=?
                WHERE id=?
                """,
                (now_text(), reviewer["account"], request_id),
            )
        notify_users(
            {request_item["requested_by"]},
            "书刊添加申请未通过",
            f"《{request_item['name']}》暂未加入馆藏。",
        )
    return True


def get_book(isbn):
    with connect_db() as db:
        row = db.execute("SELECT * FROM books WHERE isbn=?", (isbn,)).fetchone()
        return dict(row) if row else None


def search_books(query):
    query = query.strip().lower()
    if not query:
        return []
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM books WHERE enabled=1 AND item_type != 'journal_issue' AND (lower(isbn) LIKE ? OR lower(name) LIKE ? OR lower(author) LIKE ? OR lower(theme) LIKE ?) ORDER BY name",
            tuple(f"%{query}%" for _ in range(4)),
        ).fetchall()
        db.execute("INSERT INTO searches(query,count,last_used) VALUES(?,?,?) ON CONFLICT(query) DO UPDATE SET count=count+1,last_used=excluded.last_used", (query, 1, now_text()))
        return [dict(row) for row in rows]


def open_book(isbn):
    """打开书刊留言页。"""
    if get_book(isbn) is None:
        st.error("该书刊不存在或已被停用。")
        return
    st.session_state.current_book = isbn
    st.session_state.page = "首页"
    st.rerun()


def back_home_button(key):
    if st.button("返回首页", key=key):
        st.session_state.page = "首页"
        st.session_state.current_book = None
        st.session_state.current_journal = None
        st.session_state.search_query = ""
        st.session_state.search_results = []
        st.session_state.remote_results = []
        st.rerun()


def comment_rows(isbn):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT c.*, COUNT(cl.account) AS likes_count
            FROM comments c LEFT JOIN comment_likes cl ON cl.comment_id=c.id
            WHERE c.isbn=? GROUP BY c.id ORDER BY likes_count DESC, c.created_at DESC
            """,
            (isbn,),
        ).fetchall()
        return [dict(row) for row in rows]


def comment_tree(isbn, account=None):
    rows = comment_rows(isbn)
    by_parent = {}
    for row in rows:
        row["replies"] = []
        row["liked"] = False
        by_parent.setdefault(row["parent_id"], []).append(row)
    if account:
        with connect_db() as db:
            liked_ids = {row[0] for row in db.execute("SELECT comment_id FROM comment_likes WHERE account=?", (account,))}
        for row in rows:
            row["liked"] = row["id"] in liked_ids
    for row in rows:
        row["replies"] = by_parent.get(row["id"], [])
    return by_parent.get(None, [])


def comment_count(isbn):
    with connect_db() as db:
        return db.execute("SELECT COUNT(*) FROM comments WHERE isbn=?", (isbn,)).fetchone()[0]


def create_comment(isbn, parent_id, subject, content):
    user = current_user()
    if not user:
        return
    comment_id = uuid.uuid4().hex
    with connect_db() as db:
        db.execute(
            "INSERT INTO comments(id,isbn,parent_id,subject,content,name,user_account,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (comment_id, isbn, parent_id, subject.strip(), content.strip(), user.get("name", user.get("account")), user.get("account"), now_text()),
        )
    if parent_id:
        parent = get_comment(parent_id)
        if parent:
            notify_accounts = {parent["user_account"]}
            notify_users(notify_accounts, "你的留言收到新回复", f"有人回复了你在《{get_book(isbn)['name']}》下的留言。")


def get_comment(comment_id):
    with connect_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        return dict(row) if row else None


def delete_comment(comment_id):
    target = get_comment(comment_id)
    user = current_user()
    if not target or not user:
        return
    if not is_admin() and target["user_account"] != user.get("account"):
        st.error("普通用户只能删除自己的留言。")
        return
    with connect_db() as db:
        db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    if is_admin() and target["user_account"]:
        notify_users({target["user_account"]}, "你的留言已被管理员删除", f"《{get_book(target['isbn'])['name']}》中的留言已被管理员删除。")


def toggle_like(comment_id):
    user = current_user()
    if not user:
        st.info("请先登录后点赞。")
        return
    account = str(user.get("account"))
    with connect_db() as db:
        exists = db.execute("SELECT 1 FROM comment_likes WHERE comment_id=? AND account=?", (comment_id, account)).fetchone()
        if exists:
            db.execute("DELETE FROM comment_likes WHERE comment_id=? AND account=?", (comment_id, account))
        else:
            db.execute("INSERT OR IGNORE INTO comment_likes(comment_id,account) VALUES(?,?)", (comment_id, account))


def notify_users(accounts, title, body):
    actor = current_user()
    recipients = {str(account) for account in accounts if account}
    if actor:
        recipients.discard(str(actor.get("account")))
    if not recipients:
        return
    with connect_db() as db:
        for account in recipients:
            db.execute("INSERT INTO notifications(id,account,title,body,created_at,is_read) VALUES(?,?,?,?,?,0)", (uuid.uuid4().hex, account, title, body, now_text()))


def notification_rows(account):
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM notifications WHERE account=? ORDER BY is_read,created_at DESC", (account,))]


def mark_notifications_read(account):
    with connect_db() as db:
        db.execute("UPDATE notifications SET is_read=1 WHERE account=?", (account,))


def record_visit():
    if st.session_state.get("visit_recorded"):
        return
    with connect_db() as db:
        db.execute(
            "INSERT INTO visits(visit_date,count) VALUES(?,1) ON CONFLICT(visit_date) DO UPDATE SET count=count+1",
            (dt.date.today().isoformat(),),
        )
    st.session_state.visit_recorded = True


def render_reply(reply, isbn, depth):
    indent = "　" * min(depth, 8)
    st.write(f"{indent}↳ @{reply['name']} · 👍 {reply['likes_count']} · {reply['created_at']}")
    st.write(f"{indent}{reply['content']}")
    render_comment_actions(reply, isbn, depth)
    replies = reply.get("replies", [])
    if replies:
        key = f"replies_{reply['id']}"
        expanded = st.session_state.setdefault("expanded_replies", set())
        if key not in expanded:
            if st.button(f"{indent}查看回复（{len(replies)}）", key=f"show_{reply['id']}"):
                expanded.add(key)
                st.rerun()
        else:
            if st.button(f"{indent}收起回复", key=f"hide_{reply['id']}"):
                expanded.discard(key)
                st.rerun()
            limits = st.session_state.setdefault("reply_limits", {})
            limit = limits.get(key, 5)
            for child in replies[:limit]:
                render_reply(child, isbn, depth + 1)
            if limit < len(replies) and st.button(f"{indent}查看更多回复（还剩 {len(replies) - limit} 条）", key=f"more_{reply['id']}"):
                limits[key] = limit + 5
                st.rerun()


def render_comment_actions(comment, isbn, depth=0):
    columns = st.columns([1, 1, 1, 5])
    label = "取消点赞" if comment.get("liked") else "点赞"
    if columns[0].button(f"{label}（{comment['likes_count']}）", key=f"like_{comment['id']}"):
        toggle_like(comment["id"])
        st.rerun()
    if can_delete(comment) and columns[1].button("删除", key=f"delete_{comment['id']}"):
        delete_comment(comment["id"])
        st.rerun()
    if current_user() and columns[2].button("回复", key=f"reply_{comment['id']}"):
        st.session_state.reply_target = comment["id"]
        st.rerun()
    elif not current_user():
        columns[2].caption("登录后互动")
    if current_user() and st.session_state.get("reply_target") == comment["id"]:
        with st.form(f"reply_form_{comment['id']}"):
            content = st.text_area("回复内容", key=f"reply_text_{comment['id']}", height=70)
            if st.form_submit_button("提交回复"):
                if content.strip():
                    create_comment(isbn, comment["id"], "", content)
                    st.session_state.reply_target = None
                    st.rerun()
                st.warning("回复内容不能为空。")


def render_comment(comment, isbn, depth=0):
    title = comment["subject"] or f"回复 @{comment['name']}"
    with st.expander(f"{'↳ ' if depth else ''}{title} · @{comment['name']} · 👍 {comment['likes_count']}"):
        st.write(comment["content"])
        st.caption(comment["created_at"])
        render_comment_actions(comment, isbn, depth)
        replies = comment.get("replies", [])
        if replies:
            key = f"replies_{comment['id']}"
            expanded = st.session_state.setdefault("expanded_replies", set())
            if key not in expanded:
                if st.button(f"查看回复（{len(replies)}）", key=f"show_{comment['id']}"):
                    expanded.add(key)
                    st.rerun()
            else:
                if st.button("收起回复", key=f"hide_{comment['id']}"):
                    expanded.discard(key)
                    st.rerun()
                limits = st.session_state.setdefault("reply_limits", {})
                limit = limits.get(key, 5)
                for reply in replies[:limit]:
                    render_reply(reply, isbn, depth + 1)
                if limit < len(replies):
                    if st.button(f"查看更多回复（还剩 {len(replies) - limit} 条）", key=f"more_{comment['id']}"):
                        limits[key] = limit + 5
                        st.rerun()


def show_book_page(isbn):
    back_home_button(f"home_{isbn}")
    book = get_book(isbn)
    if not book:
        st.error("该书刊不存在或已被删除。")
        return
    account = current_user().get("account") if current_user() else None
    comments = comment_tree(isbn, account)
    st.header(f"{book['icon']} {book['name']}")
    st.caption(
        f"类型：{item_type_label(book)} · {item_creator_label(book)}：{book['author']} · "
        f"主题：{book['theme']} · {item_identifier_text(book)}"
    )
    if book.get("item_type") == "paper":
        if book.get("journal_name") or book.get("published_at"):
            st.caption(
                f"期刊：{book.get('journal_name') or '未知期刊'} · "
                f"发表时间：{book.get('published_at') or '未知'} · "
                f"被引：{book.get('citation_count', 0)}"
            )
        if book.get("abstract"):
            st.subheader("摘要")
            st.write(book["abstract"])
        if book.get("source_url"):
            st.markdown(f"[打开论文原文或来源页面]({book['source_url']})")
        st.link_button(
            "在新标签页打开知网检索",
            cnki_search_url(book),
            help="知网页面会在新的浏览器标签页打开；返回本标签页即可继续评论。",
        )
    st.subheader(f"留言（{len(comments)} 条）")
    if not comments:
        st.info("暂时没有留言。")
    for comment in comments:
        render_comment(comment, isbn)
    if current_user():
        with st.form(f"new_comment_{isbn}"):
            subject = st.text_input("主题")
            content = st.text_area("留言内容")
            if st.form_submit_button("提交留言"):
                if subject.strip() and content.strip():
                    create_comment(isbn, None, subject, content)
                    st.rerun()
                st.warning("主题和留言内容不能为空。")
    else:
        st.info("登录后可以发布留言、点赞和回复。")
def show_my_messages():
    back_home_button("home_from_my_messages")
    user = current_user()
    if not user:
        st.info("请先登录。")
        return
    with connect_db() as db:
        rows = [dict(row) for row in db.execute("SELECT c.*, COUNT(cl.account) likes_count FROM comments c LEFT JOIN comment_likes cl ON cl.comment_id=c.id WHERE c.user_account=? GROUP BY c.id ORDER BY likes_count DESC, c.created_at DESC", (user["account"],))]
    st.header("我的留言")
    if not rows:
        st.info("你还没有留言。")
    for row in rows:
        st.write(f"{row['subject'] or '回复'} · {row['created_at']} · 👍 {row['likes_count']}")
        st.write(row["content"])


def show_notifications():
    back_home_button("home_from_notifications")
    user = current_user()
    if not user:
        st.info("请先登录。")
        return
    rows = notification_rows(user["account"])
    st.header("通知")
    if st.button("全部标记为已读"):
        mark_notifications_read(user["account"])
        st.rerun()
    if not rows:
        st.info("暂无通知。")
    for row in rows:
        st.write(f"{'未读 · ' if not row['is_read'] else ''}{row['title']} · {row['created_at']}")
        st.info(row["body"])


def show_book_admin():
    back_home_button("home_from_book_admin")
    if not is_admin():
        st.error("只有管理员可以管理书刊。")
        return
    st.header("书刊管理")
    all_books = books(include_disabled=True)
    with st.form("add_book"):
        st.subheader("添加书籍或期刊")
        item_type = st.selectbox(
            "类型", ["book", "journal"],
            format_func=lambda value: "书籍" if value == "book" else "期刊",
        )
        isbn = st.text_input("ISBN 或 ISSN")
        name = st.text_input("书名或期刊名")
        author = st.text_input("作者或出版机构")
        theme = st.text_input("主题")
        icon = st.text_input("图标", value="📚")
        if st.form_submit_button("添加"):
            if not isbn.strip() or not name.strip():
                st.error("标识符和名称不能为空。")
            else:
                identifier = isbn.strip()
                identifier_type = "ISBN"
                if item_type == "journal":
                    normalized_issn = normalize_issn(identifier)
                    if not normalized_issn:
                        st.error("请输入有效的 ISSN，例如 0028-0836。")
                        st.stop()
                    identifier = f"ISSN:{normalized_issn}"
                    identifier_type = "ISSN"
                chosen_icon = icon.strip() or ("📰" if item_type == "journal" else "📚")
                if item_type == "journal" and chosen_icon == "📚":
                    chosen_icon = "📰"
                try:
                    with connect_db() as db:
                        db.execute(
                            """
                            INSERT INTO books(
                                isbn,name,author,theme,icon,item_type,
                                identifier_type,enabled,created_at
                            ) VALUES(?,?,?,?,?,?,?,1,?)
                            """,
                            (
                                identifier, name.strip(), author.strip(), theme.strip(),
                                chosen_icon,
                                item_type, identifier_type, now_text(),
                            ),
                        )
                    st.success("书刊已添加。")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("该 ISBN 或 ISSN 已存在。")
    if all_books:
        selected = st.selectbox("选择要编辑的书刊", [book["isbn"] for book in all_books])
        book = next(book for book in all_books if book["isbn"] == selected)
        with st.form(f"edit_book_{selected}"):
            item_type = book.get("item_type", "book")
            st.text_input("类型", value=item_type_label(book), disabled=True)
            name = st.text_input("书名或期刊名", value=book["name"])
            author = st.text_input("作者或出版机构", value=book["author"])
            theme = st.text_input("主题", value=book["theme"])
            icon = st.text_input("图标", value=book["icon"])
            enabled = st.checkbox("启用", value=bool(book["enabled"]))
            if st.form_submit_button("保存修改"):
                with connect_db() as db:
                    db.execute(
                        """
                        UPDATE books
                        SET name=?,author=?,theme=?,icon=?,item_type=?,identifier_type=?,enabled=?
                        WHERE isbn=?
                        """,
                        (
                            name.strip(), author.strip(), theme.strip(),
                            icon.strip() or ("📰" if item_type == "journal" else "📚"),
                            item_type, book.get("identifier_type", "ISBN"),
                            int(enabled), selected,
                        ),
                    )
                st.success("书刊已更新。")
                st.rerun()
        if comment_count(selected) == 0 and st.button("删除该书刊", key=f"remove_book_{selected}"):
            with connect_db() as db:
                db.execute("DELETE FROM books WHERE isbn=?", (selected,))
            st.success("书刊已删除。")
            st.rerun()
        elif comment_count(selected):
            st.caption("该书刊已有留言，不能删除；可以停用。")


def show_all_books():
    back_home_button("home_from_all_books")
    st.header("全部书刊")
    all_books = books()
    if not all_books:
        st.info("馆藏中暂时没有书籍或期刊。")
        return
    cols = st.columns(3)
    for index, book in enumerate(all_books):
        with cols[index % 3]:
            st.write(f"{book['icon']} **{book['name']}**")
            st.caption(
                f"{item_type_label(book)} · {book['author']} · {book['theme']} · "
                f"留言 {comment_count(book['isbn'])}"
            )
            if st.button("查看留言", key=f"all_book_{book['isbn']}"):
                open_catalog_item(book)


def show_journal_issues():
    journal = st.session_state.get("current_journal") or {}
    back_home_button("home_from_journal_issues")
    if not journal:
        st.info("没有选择期刊。")
        return
    st.header(f"{journal.get('icon', '📰')} {journal.get('name', '期刊')}：所有期次")
    st.caption(
        f"出版机构：{journal.get('author', '未知出版机构')} · "
        f"{item_identifier_text(journal)}"
    )
    if journal.get("item_type") != "journal":
        st.error("当前对象不是期刊。")
        return
    issues = journal_issue_rows(journal["isbn"])
    if not issues:
        with st.spinner("正在从 Crossref 获取期次……"):
            issues = lookup_crossref_journal_issues(journal["isbn"])
            if issues:
                save_journal_issues(journal, issues)
                issues = journal_issue_rows(journal["isbn"])
    if not issues:
        st.info("暂时没有获取到该期刊的期次。部分期刊可能未将卷期信息完整登记到 Crossref。")
        return
    st.caption(f"共显示 {len(issues)} 个 Crossref 收录期次；每个期次都有独立留言区。")
    for issue in issues:
        st.write(f"{issue['icon']} **{issue['name']}**")
        st.caption(f"{item_identifier_text(issue)} · 留言 {comment_count(issue['isbn'])}")
        if issue.get("url"):
            st.caption(issue["url"])
        if st.button("查看本期期次留言", key=f"issue_{issue['isbn']}"):
            open_book(issue["isbn"])


def cnki_search_url(item):
    """生成知网检索链接；知网阅读和账号权限仍由知网页面负责。"""
    title = str(item.get("name", "")).strip()
    doi = str(item.get("doi", "")).strip()
    query = " ".join(part for part in (title, doi) if part)
    return f"https://kns.cnki.net/kns8s/defaultresult/index?kw={quote(query)}"


def show_book_requests_admin():
    back_home_button("home_from_book_requests")
    if not is_admin():
        st.error("只有管理员可以审核书刊申请。")
        return
    st.header("书刊添加申请")
    requests = pending_book_requests()
    if not requests:
        st.info("暂无待审核申请。")
        return
    for item in requests:
        st.write(
            f"**{item['name']}** · {item_type_label(item)} · {item['author']} · "
            f"{item_identifier_text(item)}"
        )
        st.caption(f"申请账号：{item['requested_by']} · {item['created_at']}")
        approve_col, reject_col, _ = st.columns([1, 1, 5])
        if approve_col.button("批准", key=f"approve_request_{item['id']}"):
            if review_book_request(item["id"], True):
                st.success("已加入馆藏并通知申请者。")
                st.rerun()
        if reject_col.button("拒绝", key=f"reject_request_{item['id']}"):
            if review_book_request(item["id"], False):
                st.success("已拒绝并通知申请者。")
                st.rerun()
        st.divider()


def account_panel():
    user = current_user()
    if user:
        unread = len([row for row in notification_rows(user["account"]) if not row["is_read"]])
        st.sidebar.write(f"已登录：{user['name']}{'（管理员）' if is_admin() else ''}")
        if st.sidebar.button(f"通知（{unread}）"):
            st.session_state.page = "通知"
            st.session_state.current_book = None
            st.rerun()
        if is_admin():
            if st.sidebar.button(f"书刊申请（{pending_request_count()}）"):
                st.session_state.page = "书刊申请"
                st.session_state.current_book = None
                st.rerun()
            if st.sidebar.button("书刊管理"):
                st.session_state.page = "书刊管理"
                st.session_state.current_book = None
                st.rerun()
        if st.sidebar.button("我的留言"):
            st.session_state.page = "我的留言"
            st.session_state.current_book = None
            st.rerun()
        if st.sidebar.button("退出登录"):
            st.session_state.user = None
            st.session_state.page = "首页"
            st.session_state.current_book = None
            st.rerun()
        return
    mode = st.sidebar.radio("账户", ["登录", "注册"], horizontal=True)
    if mode == "注册":
        with st.sidebar.form("register"):
            account = st.text_input("账号")
            name = st.text_input("昵称")
            password = st.text_input("密码", type="password")
            confirm = st.text_input("确认密码", type="password")
            submit = st.form_submit_button("注册")
        if submit:
            if not account.strip() or not password:
                st.sidebar.error("账号和密码不能为空。")
            elif account.strip() == ADMIN_ACCOUNT or account.strip() in admin_accounts_from_secrets():
                st.sidebar.error("管理员账号不能注册为普通用户。")
            elif password != confirm:
                st.sidebar.error("两次密码不一致。")
            else:
                try:
                    with connect_db() as db:
                        db.execute("INSERT INTO users(account,name,password_hash,created_at) VALUES(?,?,?,?)", (account.strip(), name.strip() or account.strip(), password_hash(password), now_text()))
                    st.sidebar.success("注册成功，请登录。")
                except sqlite3.IntegrityError:
                    st.sidebar.error("该账号已存在。")
    else:
        with st.sidebar.form("login"):
            account = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submit = st.form_submit_button("登录")
        if submit:
            account = account.strip()
            admin = admin_accounts_from_secrets().get(account)
            if admin and password == admin["password"]:
                st.session_state.user = {"account": account, "name": admin["name"], "role": "admin"}
                st.rerun()
            with connect_db() as db:
                user = db.execute("SELECT * FROM users WHERE account=?", (account,)).fetchone()
            if user and user["password_hash"] == password_hash(password):
                st.session_state.user = {"account": account, "name": user["name"], "role": "user"}
                st.rerun()
            st.sidebar.error("账号或密码错误。")


init_db()
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "首页"
if "current_book" not in st.session_state:
    st.session_state.current_book = None
if "current_journal" not in st.session_state:
    st.session_state.current_journal = None
if "expanded_replies" not in st.session_state:
    st.session_state.expanded_replies = set()
if "reply_limits" not in st.session_state:
    st.session_state.reply_limits = {}
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "remote_results" not in st.session_state:
    st.session_state.remote_results = []
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "search_kind" not in st.session_state:
    st.session_state.search_kind = "book"
record_visit()


with st.sidebar:
    st.header("账户")
    account_panel()
    st.divider()
    search_kind = st.radio(
        "搜索类型",
        ["book", "journal", "paper"],
        index={"book": 0, "journal": 1, "paper": 2}.get(st.session_state.search_kind, 0),
        format_func=lambda value: {
            "book": "搜索书籍",
            "journal": "搜索期刊",
            "paper": "搜索论文",
        }[value],
        horizontal=True,
    )
    with st.form("search"):
        query = st.text_input(
            "搜索书名、作者或 ISBN"
            if search_kind == "book"
            else "搜索论文标题、作者、关键词或 DOI"
            if search_kind == "paper"
            else "搜索期刊名、出版机构或 ISSN"
        )

        if st.form_submit_button("搜索"):
            query = query.strip()
            st.session_state.search_kind = search_kind
            st.session_state.search_query = query
            st.session_state.search_results = search_books(query) if search_kind in ("book", "paper") else []
            st.session_state.remote_results = []
            st.session_state.page = "首页"
            st.session_state.current_book = None
            st.session_state.current_journal = None

            if query:
                if search_kind == "journal":
                    remote_results = normalize_remote_results(
                        lookup_crossref_journals(query) + lookup_wikidata(query),
                        query,
                    )
                elif search_kind == "paper":
                    remote_results = normalize_remote_results(
                        lookup_openalex_papers(query),
                        query,
                    )
                else:
                    remote_results = normalize_remote_results(
                        lookup_open_library(query)
                        + lookup_google_books(query)
                        + lookup_wikidata(query),
                        query,
                    )
                local_ids = {book["isbn"] for book in books(include_disabled=True)}
                st.session_state.remote_results = [
                    item for item in remote_results if item["isbn"] not in local_ids
                ]
    st.file_uploader("上传旧照片", type=["jpg", "jpeg", "png"])


st.title("图书馆跨时空留言板")
page = st.session_state.page
if st.session_state.current_book:
    show_book_page(st.session_state.current_book)
elif page == "我的留言":
    show_my_messages()
elif page == "通知":
    show_notifications()
elif page == "书刊管理":
    show_book_admin()
elif page == "书刊申请":
    show_book_requests_admin()
elif page == "全部书刊":
    show_all_books()
elif page == "期刊期次":
    show_journal_issues()
else:
    results = st.session_state.get("search_results", [])
    if st.session_state.get("search_query"):
        st.subheader(f"搜索结果：{st.session_state.search_query}")
        for book in results:
            if st.button(
                f"{book['icon']} {book['name']} · {item_type_label(book)} · "
                f"{item_identifier_text(book)}",
                key=f"result_{book['isbn']}",
            ):
                open_catalog_item(book)
    remote_results = st.session_state.get("remote_results", [])

    if remote_results:
        st.subheader("在线资料")

        for book in remote_results:
            st.write(
                f"{book['icon']} **{book['name']}**"
                f" · {item_type_label(book)}"
                f" · {item_creator_label(book)}：{book['author']}"
                f" · {item_identifier_text(book)}"
            )

            if book.get("item_type") == "journal" and st.button(
                "查看所有期次", key=f"issues_{book['isbn']}"
            ):
                st.session_state.current_journal = book
                st.session_state.page = "期刊期次"
                st.session_state.current_book = None
                st.rerun()

            if is_admin():
                if st.button(
                        "导入馆藏",
                        key=f"import_{book['isbn']}"
                ):
                    save_remote_book(book)
                    st.session_state.remote_results = []
                    st.success("书刊已自动导入馆藏。")
                    st.rerun()
            else:
                user = current_user()
                if not user:
                    st.caption("登录后可以向管理员申请添加。")
                else:
                    status = book_request_status(book["isbn"], user["account"])
                    if status == "added" or status == "approved":
                        st.caption("该书刊已加入馆藏。")
                    elif status == "pending":
                        st.caption("已申请，等待管理员审核。")
                    elif st.button("申请添加", key=f"request_{book['isbn']}"):
                        create_book_request(book, user["account"])
                        st.success("申请已提交，管理员审核后会通知你。")
                        st.rerun()

    if st.session_state.get("search_query") and not results and not remote_results:
        kind_label = {
            "book": "书籍",
            "journal": "期刊",
            "paper": "论文",
        }.get(st.session_state.get("search_kind"), "资料")
        st.info(f"本地馆藏和在线资料库都没有找到相关{kind_label}，或在线服务暂时不可用。")

    st.subheader("热门书刊")
    visible_books = popular_books(6)
    cols = st.columns(3)
    for index, book in enumerate(visible_books):
        with cols[index % 3]:
            st.write(f"{book['icon']} **{book['name']}**")
            st.caption(
                f"{item_type_label(book)} · {book['author']} · {book['theme']} · "
                f"留言 {comment_count(book['isbn'])}"
            )
            button_label = "查看所有期次" if book.get("item_type") == "journal" else "查看留言"
            if st.button(button_label, key=f"book_{book['isbn']}"):
                open_catalog_item(book)
    if st.button("查看全部书刊"):
        st.session_state.page = "全部书刊"
        st.session_state.current_book = None
        st.rerun()
    st.subheader("热门搜索")
    with connect_db() as db:
        hot_searches = [row[0] for row in db.execute("SELECT query FROM searches ORDER BY count DESC, last_used DESC LIMIT 10")]
        stats = db.execute("SELECT COALESCE(SUM(count),0) FROM visits").fetchone()[0]
    st.info("暂无热门搜索。" if not hot_searches else "、".join(hot_searches))
    st.subheader("访问统计")
    st.info("暂无访问统计。" if not stats else f"累计访问：{stats}")
