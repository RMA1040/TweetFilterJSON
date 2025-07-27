import streamlit as st
import json
from fpdf import FPDF
import io
from datetime import datetime
import re
import warnings
warnings.filterwarnings("ignore", message="cmap value too big/small")

# Inlog via secrets
users = st.secrets["users"]

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("Login vereist")
    username = st.text_input("Gebruikersnaam")
    password = st.text_input("Wachtwoord", type="password")

    if st.button("Log in"):
        if username in users and users[username] == password:
            st.session_state["logged_in"] = True
            st.success(f"Ingelogd als {username}")
        else:
            st.error("Ongeldige gebruikersnaam of wachtwoord")
    st.stop()

with st.sidebar:
    if st.button("Log uit"):
        st.session_state["logged_in"] = False

def evaluate_search_query(text, query):
    def escape_word(w):
        return f'"{w.lower()}" in text_lower'

    tokens = re.findall(r'\"(.*?)\"|\bAND\b|\bOR\b|\(|\)', query)
    if not tokens:
        return True

    logic = []
    for token in tokens:
        if token == 'AND':
            logic.append('and')
        elif token == 'OR':
            logic.append('or')
        elif token == '(' or token == ')':
            logic.append(token)
        elif token:
            logic.append(escape_word(token))

    final_expr = ' '.join(logic)
    text_lower = text.lower()
    try:
        return eval(final_expr)
    except Exception as e:
        print(f"Evaluatiefout: {e}")
        return False

def filter_tweets(tweets, min_words=0, max_words=None, required_keywords=None, use_or=False,
                  filter_metric=None, min_metric_value=0, search_query="",
                  from_date=None, to_date=None):
    filtered = []
    for i, tweet in enumerate(tweets):
        try:
            text = tweet.get("text", "")
            word_count = len(text.split())
            if word_count < min_words or (max_words is not None and word_count > max_words):
                continue

            if search_query:
                if not evaluate_search_query(text, search_query):
                    continue

            if required_keywords:
                text_lower = text.lower()
                if use_or:
                    if not any(k.lower() in text_lower for k in required_keywords):
                        continue
                else:
                    if not all(k.lower() in text_lower for k in required_keywords):
                        continue

            if filter_metric:
                metrics = tweet.get("public_metrics", {}) or {}
                metric_value = int(metrics.get(filter_metric, 0) or 0)
                if metric_value < min_metric_value:
                    continue

            created_at_full = tweet.get("created_at", None)
            if created_at_full:
                try:
                    dt = datetime.fromisoformat(created_at_full.replace("Z", "+00:00"))
                    tweet["created_date"] = dt.date().isoformat()
                except Exception:
                    tweet["created_date"] = "onbekend"
            else:
                tweet["created_date"] = "onbekend"
            # Filteren op datum (optioneel)
            if from_date and tweet["created_date"] != "onbekend":
                if tweet["created_date"] < from_date.isoformat():
                    continue

            if to_date and tweet["created_date"] != "onbekend":
                if tweet["created_date"] > to_date.isoformat():
                    continue
            filtered.append(tweet)
        except Exception as e:
            st.warning(f"Tweet op index {i} veroorzaakte een fout: {e}")
    return filtered

def generate_txt(tweets):
    lines = []
    for i, tweet in enumerate(tweets):
        text = tweet.get("text", "")
        metrics = tweet.get("public_metrics", {}) or {}
        reply_count = metrics.get("reply_count", "Onbekend")
        retweet_count = metrics.get("retweet_count", "Onbekend")
        like_count = metrics.get("like_count", "Onbekend")
        created_date = tweet.get("created_date", "onbekend")

        lines.append(
            f"Tweet {i+1}:\n{text}\n"
            f"Replies: {reply_count} | Retweets: {retweet_count} | Created at: {created_date} | Likes: {like_count}\n"
            + "-"*40 + "\n"
        )
    return "\n".join(lines)

def safe_multicell(pdf, text):
    try:
        if text.strip() == "":
            text = "[Lege tweet]"
        max_len = 1000
        if len(text) > max_len:
            text = text[:max_len] + "\n[...tekst afgekapt...]"
        pdf.multi_cell(0, 10, txt=text)
    except Exception as e:
        pdf.cell(0, 10, txt="[Fout bij weergeven tweet]", ln=True)

def generate_pdf(tweets):
    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
    except:
        pdf.set_font("Arial", size=12)

    for i, tweet in enumerate(tweets):
        try:
            text = tweet.get("text", "")
            metrics = tweet.get("public_metrics", {}) or {}
            reply_count = metrics.get("reply_count", "Onbekend")
            retweet_count = metrics.get("retweet_count", "Onbekend")
            like_count = metrics.get("like_count", "Onbekend")
            quote_count = metrics.get("quote_count", "Onbekend")
            bookmark_count = metrics.get("bookmark_count", "Onbekend")
            impression_count = metrics.get("impression_count", "Onbekend")
            created_date = tweet.get("created_date", "onbekend")

            combined = (
                f"Tweet {i+1}:\n{text}\n\n"
                f"Aangemaakt op: {created_date}\n"
                f"Replies: {reply_count} | Retweets: {retweet_count} | Likes: {like_count}\n"
                f"Quotes: {quote_count} | Bookmarks: {bookmark_count} | Impressions: {impression_count}\n\n"
                + "-"*80 + "\n"
            )
            if combined.strip():
                safe_multicell(pdf, combined)
            else:
                pdf.cell(0, 10, txt="[Lege tweet]", ln=True)
        except Exception as e:
            pdf.cell(0, 10, txt="[Fout bij tweet]", ln=True)

    try:
        return io.BytesIO(pdf.output(dest='S').encode('latin1', errors='ignore'))
    except:
        return io.BytesIO(b"PDF generatie mislukt.")

# --- UI Start ---
st.title("Tweet Filter op Woorden en Inhoud")

uploaded_file = st.file_uploader("Upload een JSON-bestand met tweets", type="json")

if uploaded_file is not None:
    try:
        json_data = json.load(uploaded_file)

        if isinstance(json_data, dict) and isinstance(json_data.get("data"), list):
            tweets = json_data["data"]
        elif isinstance(json_data, list):
            tweets = json_data
        else:
            st.error("JSON-bestand bevat geen lijst van tweets.")
            tweets = []

        if tweets:
            st.write("Eerste 3 tweets ter controle:")
            st.json(tweets[:3])

            min_words = st.number_input("Minimum aantal woorden", min_value=0, value=3)
            max_words = st.number_input("Maximum aantal woorden (optioneel)", min_value=0, value=0)

            keyword_input = st.text_input("Trefwoorden (extra filter, komma's)", "")
            required_keywords = [kw.strip() for kw in keyword_input.split(',') if kw.strip()]
            use_or = st.checkbox("Gebruik 'OR' voor trefwoorden", value=False)

            search_query = st.text_area(
                "Geavanceerde zoekopdracht (bijv. \"airborne AND droplet\" OR \"aerosol AND transmission\")", "")

            filter_metric = st.selectbox(
                "Filter op minimaal aantal (optioneel)",
                options=["", "retweet_count", "like_count", "reply_count", "quote_count"],
                format_func=lambda x: x.replace("_count", "").capitalize() if x else "Geen filter"
            )

            min_metric_value = 0
            if filter_metric:
                min_metric_value = st.number_input(
                    f"Minimum aantal {filter_metric.replace('_count','')}s", min_value=0, value=0)

            from_date = st.date_input("Vanaf datum (optioneel)", value=None)
            to_date = st.date_input("Tot en met datum (optioneel)", value=None)

            if st.button("Filter tweets"):
                max_words_value = max_words if max_words > 0 else None

                filtered = filter_tweets(
                    tweets,
                    min_words=min_words,
                    max_words=max_words_value,
                    required_keywords=required_keywords,
                    use_or=use_or,
                    filter_metric=filter_metric if filter_metric else None,
                    min_metric_value=min_metric_value,
                    search_query=search_query,
                    from_date=from_date,
                    to_date=to_date
                )

                sort_metric = filter_metric if filter_metric else "reply_count"
                filtered.sort(
                    key=lambda t: t.get("public_metrics", {}).get(sort_metric, 0) or 0,
                    reverse=True
                )

                st.success(f"{len(filtered)} tweets gevonden.")

                for i, tweet in enumerate(filtered):
                    text = tweet.get("text", "")
                    metrics = tweet.get("public_metrics", {}) or {}
                    created_date = tweet.get("created_date", "onbekend")
                    st.markdown(f"### Tweet {i+1} — {created_date}")
                    st.write(text)
                    st.markdown(
                        f"**Replies:** {metrics.get('reply_count', 0)} | **Retweets:** {metrics.get('retweet_count', 0)} | "
                        f"**Likes:** {metrics.get('like_count', 0)} | **Quotes:** {metrics.get('quote_count', 0)}"
                    )
                    st.markdown("---")

                st.download_button("Download als JSON", json.dumps(filtered, ensure_ascii=False, indent=2),
                                   file_name="filtered_tweets.json", mime="application/json")

                st.download_button("Download als TXT", generate_txt(filtered),
                                   file_name="filtered_tweets.txt", mime="text/plain")

                st.download_button("Download als PDF", generate_pdf(filtered),
                                   file_name="filtered_tweets.pdf", mime="application/pdf")

        else:
            st.warning("Geen tweets gevonden in het JSON-bestand.")
    except Exception as e:
        st.exception(f"Fout bij verwerken van JSON-bestand: {e}")
st.markdown(
    """
    <footer style="text-align:center; margin-top:50px;">
        <hr>
        <p>Raymond Maetha <a href="https://www.linkedin.com/in/raymond-maetha-5901b3203/" target="_blank">LinkedIn</a></p>
    </footer>
    """,
    unsafe_allow_html=True
)
