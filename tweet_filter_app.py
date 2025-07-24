import streamlit as st
import json
from fpdf import FPDF
import io
import warnings
warnings.filterwarnings("ignore", message="cmap value too big/small")

# Ophalen uit secrets
users = st.secrets["users"]

# Inlog status behouden
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

#uitloggen
# Toon log-uit knop als gebruiker ingelogd is
if st.session_state["logged_in"]:
    with st.sidebar:
        if st.button("Log uit"):
            st.session_state["logged_in"] = False

def count_words(text):
    return len(text.split())

def contains_keywords(text, keywords):
    text_lower = text.lower()
    return all(word.lower() in text_lower for word in keywords)

def contains_keywords_or(text, keywords):
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in keywords)

def filter_tweets(tweets, min_words=0, max_words=None, required_keywords=None, use_or=False, filter_metric=None, min_metric_value=0):
    filtered = []
    for i, tweet in enumerate(tweets):
        try:
            text = tweet.get("text", "")
            word_count = len(text.split())
            if word_count >= min_words and (max_words is None or word_count <= max_words):
                if required_keywords:
                    if use_or:
                        if not contains_keywords_or(text, required_keywords):
                            continue
                    else:
                        if not contains_keywords(text, required_keywords):
                            continue

                # Filter op metriek (retweets, likes, replies)
                if filter_metric:
                    metrics = tweet.get("public_metrics", {}) or {}
                    metric_value = metrics.get(filter_metric, 0) or 0
                    if metric_value < min_metric_value:
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

        lines.append(f"Tweet {i+1}:\n{text}\nReplies: {reply_count} | Retweets: {retweet_count} | Likes: {like_count}\n{'-'*40}\n")

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
        print(f"multi_cell-fout: {e}")
        pdf.cell(0, 10, txt="[Fout bij weergeven tweet]", ln=True)

def generate_pdf(tweets):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_title("")
    pdf.set_author("")
    pdf.set_creator("")
    pdf.set_subject("")
    pdf.set_keywords("")

    try:
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
    except:
        pdf.set_font("Arial", size=12)

    for i, tweet in enumerate(tweets):
        try:
            if not isinstance(tweet, dict):
                continue
            text = tweet.get("text", "")
            if not isinstance(text, str):
                text = ""

            metrics = tweet.get("public_metrics", {}) or {}
            reply_count = metrics.get("reply_count", "Onbekend")
            retweet_count = metrics.get("retweet_count", "Onbekend")
            like_count = metrics.get("like_count", "Onbekend")
            quote_count = metrics.get("quote_count", "Onbekend")
            bookmark_count = metrics.get("bookmark_count", "Onbekend")
            impression_count = metrics.get("impression_count", "Onbekend")

            combined = (
                f"Tweet {i+1}:\n{text}\n\n"
                f"Replies: {reply_count} | Retweets: {retweet_count} | Likes: {like_count}\n"
                f"Quotes: {quote_count} | Bookmarks: {bookmark_count} | Impressions: {impression_count}\n\n"
                + "-"*80 + "\n"
            )

            if combined.strip():
                safe_multicell(pdf, combined)
            else:
                pdf.cell(0, 10, txt="[Lege tweet]", ln=True)
        except Exception as e:
            print(f"Fout bij verwerken van tweet index {i}: {e}")
            pdf.cell(0, 10, txt="[Fout bij tweet]", ln=True)

    try:
        pdf_output = pdf.output(dest='S').encode('latin1', errors='ignore')
    except Exception as e:
        print(f"Fout bij genereren van PDF-output: {e}")
        return io.BytesIO(b"PDF generatie mislukt.")

    return io.BytesIO(pdf_output)


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

        if not isinstance(tweets, list):
            st.error("JSON bevat geen geldige lijst met tweets.")
            tweets = []

        if not tweets:
            st.warning("Geen tweets gevonden in het JSON-bestand.")
        else:
            st.write("Eerste 3 tweets ter controle:")
            st.json(tweets[:3])
            min_words = st.number_input("Minimum aantal woorden", min_value=0, value=3)
            max_words = st.number_input("Maximum aantal woorden (optioneel)", min_value=0, value=0)

            keyword_input = st.text_input("Tweets moeten deze woorden bevatten (gescheiden door komma's)", "")
            required_keywords = [kw.strip() for kw in keyword_input.split(',') if kw.strip()]

            use_or = st.checkbox("Gebruik 'OR' voor trefwoorden (anders 'AND')", value=False)

            filter_metric = st.selectbox(
                "Filter op minimaal aantal (optioneel)",
                options=["", "retweet_count", "like_count", "reply_count", "quote_count"],
                format_func=lambda x: x.replace("_count", "").capitalize() if x else "Geen filter"
            )

            min_metric_value = 0
            if filter_metric:
                min_metric_value = st.number_input(f"Minimum aantal {filter_metric.replace('_count','')}s", min_value=0, value=0)

            if st.button("Filter tweets"):
                max_words_value = max_words if max_words > 0 else None

                filtered = filter_tweets(
                    tweets,
                    min_words=min_words,
                    max_words=max_words_value,
                    required_keywords=required_keywords,
                    use_or=use_or,
                    filter_metric=filter_metric if filter_metric else None,
                    min_metric_value=min_metric_value
                )

                # Sorteer op gekozen metriek, standaard replies
                sort_metric = filter_metric if filter_metric else "reply_count"
                filtered.sort(
                    key=lambda t: t.get("public_metrics", {}).get(sort_metric, 0) or 0,
                    reverse=True
                )

                st.success(f"{len(filtered)} tweets gevonden.")

                for i, tweet in enumerate(filtered):
                    text = tweet.get("text", "")
                    metrics = tweet.get("public_metrics", {}) or {}
                    reply_count = metrics.get("reply_count", 0)
                    retweet_count = metrics.get("retweet_count", 0)
                    like_count = metrics.get("like_count", 0)
                    quote_count = metrics.get("quote_count", 0)

                    st.markdown(f"### Tweet {i+1}")
                    st.write(text)
                    st.markdown(
                        f"**Replies:** {reply_count} | **Retweets:** {retweet_count} | **Likes:** {like_count} | **Quotes:** {quote_count}"
                    )
                    st.markdown("---")

                output_json = json.dumps(filtered, ensure_ascii=False, indent=2)
                st.download_button("Download als JSON", output_json, file_name="filtered_tweets.json", mime="application/json")

                txt_output = generate_txt(filtered)
                st.download_button("Download als TXT", txt_output, file_name="filtered_tweets.txt", mime="text/plain")

                pdf_file = generate_pdf(filtered)
                st.download_button("Download als PDF", pdf_file, file_name="filtered_tweets.pdf", mime="application/pdf")

    except Exception as e:
        st.exception(f"Fout bij verwerken van JSON-bestand: {e}")
