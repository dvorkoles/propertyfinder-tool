import streamlit as st
import requests
import re
import json
import hashlib
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


st.set_page_config(
    page_title="Property Finder Tool",
    page_icon="🏠",
    layout="wide"
)


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def first_value(data, keys):
    """
    Find the first non-empty value for a list of possible keys.
    """
    if not isinstance(data, dict):
        return ""

    lowered = {
        str(k).lower(): v
        for k, v in data.items()
    }

    for key in keys:
        value = lowered.get(key.lower())

        if value not in (None, "", [], {}):
            return value

    return ""


def make_absolute_url(url, base_url):
    if not url:
        return ""

    url = str(url)

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return urljoin(base_url, url)


def normalize_image(value, base_url):
    if isinstance(value, list) and value:
        value = value[0]

    if isinstance(value, dict):
        value = (
            value.get("url")
            or value.get("src")
            or value.get("image")
            or ""
        )

    return make_absolute_url(value, base_url)


# ---------------------------------------------------------
# FETCH PAGE
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text, response.status_code


# ---------------------------------------------------------
# JSON EXTRACTION
# ---------------------------------------------------------

def collect_dicts(obj, output):
    """
    Recursively collect dictionaries from JSON.
    """

    if isinstance(obj, dict):
        output.append(obj)

        for value in obj.values():
            collect_dicts(value, output)

    elif isinstance(obj, list):
        for item in obj:
            collect_dicts(item, output)


def extract_json_objects(html):
    objects = []

    soup = BeautifulSoup(html, "html.parser")

    # JSON-LD
    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"}
    ):
        try:
            parsed = json.loads(script.string or script.get_text())
            collect_dicts(parsed, objects)
        except Exception:
            pass

    # Generic JSON script blocks
    for script in soup.find_all("script"):
        text = script.string or script.get_text()

        if not text:
            continue

        text = text.strip()

        if not text:
            continue

        # Only attempt JSON-looking blocks
        if (
            text.startswith("{")
            or text.startswith("[")
        ):
            try:
                parsed = json.loads(text)
                collect_dicts(parsed, objects)
            except Exception:
                pass

    return objects


# ---------------------------------------------------------
# LISTING DETECTION
# ---------------------------------------------------------

LISTING_KEYS = [
    "propertyid",
    "property_id",
    "listingid",
    "listing_id",
    "property",
    "listing",
    "bedrooms",
    "baths",
    "bathrooms",
    "price",
    "reference",
    "area",
]


def looks_like_listing(data):
    if not isinstance(data, dict):
        return False

    keys = {
        str(k).lower()
        for k in data.keys()
    }

    matches = len(keys.intersection(LISTING_KEYS))

    # A listing normally has several property-related fields.
    return matches >= 2


# ---------------------------------------------------------
# NORMALIZE LISTING
# ---------------------------------------------------------

def normalize_listing(data, base_url):
    if not isinstance(data, dict):
        return None

    if not looks_like_listing(data):
        return None

    listing_id = first_value(
        data,
        [
            "listingId",
            "listing_id",
            "propertyId",
            "property_id",
            "id"
        ]
    )

    reference = first_value(
        data,
        [
            "reference",
            "referenceNumber",
            "propertyReference",
            "ref"
        ]
    )

    title = first_value(
        data,
        [
            "title",
            "name",
            "propertyTitle"
        ]
    )

    description = first_value(
        data,
        [
            "description",
            "propertyDescription"
        ]
    )

    price = first_value(
        data,
        [
            "price",
            "priceValue",
            "amount"
        ]
    )

    bedrooms = first_value(
        data,
        [
            "bedrooms",
            "bedroom",
            "beds"
        ]
    )

    bathrooms = first_value(
        data,
        [
            "bathrooms",
            "bathroom",
            "baths"
        ]
    )

    area = first_value(
        data,
        [
            "area",
            "size",
            "builtUpArea",
            "built_up_area"
        ]
    )

    community = first_value(
        data,
        [
            "community",
            "communityName",
            "location",
            "locationName",
            "areaName"
        ]
    )

    property_type = first_value(
        data,
        [
            "propertyType",
            "property_type",
            "type"
        ]
    )

    url = first_value(
        data,
        [
            "url",
            "link",
            "propertyUrl",
            "listingUrl"
        ]
    )

    image = first_value(
        data,
        [
            "image",
            "imageUrl",
            "image_url",
            "photo",
            "thumbnail"
        ]
    )

    url = make_absolute_url(url, base_url)
    image = normalize_image(image, base_url)

    # Sometimes location is nested.
    if isinstance(community, dict):
        community = (
            community.get("name")
            or community.get("title")
            or ""
        )

    listing = {
        "id": clean_text(listing_id),
        "reference": clean_text(reference),
        "title": clean_text(title),
        "property_type": clean_text(property_type),
        "community": clean_text(community),
        "bedrooms": clean_text(bedrooms),
        "bathrooms": clean_text(bathrooms),
        "area": clean_text(area),
        "price": clean_text(price),
        "url": clean_text(url),
        "image": clean_text(image),
        "description": clean_text(description),
    }

    # Require at least some meaningful property information.
    useful_fields = [
        listing["id"],
        listing["reference"],
        listing["title"],
        listing["community"],
        listing["price"],
        listing["bedrooms"],
        listing["area"],
    ]

    if sum(bool(x) for x in useful_fields) < 2:
        return None

    return listing


# ---------------------------------------------------------
# HTML FALLBACK
# ---------------------------------------------------------

def extract_links_from_html(html, base_url):
    """
    Fallback parser for listing URLs visible in HTML.
    """

    soup = BeautifulSoup(html, "html.parser")

    results = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")

        if not href:
            continue

        full_url = make_absolute_url(href, base_url)

        # Property Finder property/listing URLs generally contain
        # property-related paths. We intentionally do not attempt
        # to bypass bot protection or private APIs.
        if "property" not in full_url.lower():
            continue

        text = clean_text(a.get_text(" "))

        if not text:
            continue

        results.append(
            {
                "id": "",
                "reference": "",
                "title": text[:200],
                "property_type": "",
                "community": "",
                "bedrooms": "",
                "bathrooms": "",
                "area": "",
                "price": "",
                "url": full_url,
                "image": "",
                "description": "",
            }
        )

    return results


# ---------------------------------------------------------
# DEDUPLICATION
# ---------------------------------------------------------

def normalize_for_hash(value):
    value = clean_text(value).lower()

    value = re.sub(
        r"[^a-z0-9а-яё]+",
        "",
        value
    )

    return value


def listing_fingerprint(listing):
    """
    Fingerprint based on the same logic we discussed:
    strongest identifiers first, then property characteristics.
    """

    # Strongest identifier:
    if listing.get("id"):
        return "id:" + normalize_for_hash(listing["id"])

    if listing.get("reference"):
        return "ref:" + normalize_for_hash(
            listing["reference"]
        )

    fields = [
        listing.get("community", ""),
        listing.get("property_type", ""),
        listing.get("bedrooms", ""),
        listing.get("bathrooms", ""),
        listing.get("area", ""),
        listing.get("price", ""),
        listing.get("title", ""),
    ]

    raw = "|".join(
        normalize_for_hash(x)
        for x in fields
    )

    return "fp:" + hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()


def deduplicate_listings(listings):
    unique = {}
    duplicates = 0

    for listing in listings:
        fingerprint = listing_fingerprint(listing)

        if fingerprint in unique:
            duplicates += 1

            # Prefer the version containing more information.
            old_score = sum(
                bool(v)
                for v in unique[fingerprint].values()
            )

            new_score = sum(
                bool(v)
                for v in listing.values()
            )

            if new_score > old_score:
                unique[fingerprint] = listing

        else:
            unique[fingerprint] = listing

    return list(unique.values()), duplicates


# ---------------------------------------------------------
# MAIN EXTRACTION
# ---------------------------------------------------------

def extract_listings(html, base_url):
    objects = extract_json_objects(html)

    listings = []

    for obj in objects:
        listing = normalize_listing(
            obj,
            base_url
        )

        if listing:
            listings.append(listing)

    # HTML fallback
    if not listings:
        listings.extend(
            extract_links_from_html(
                html,
                base_url
            )
        )

    return listings


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------

st.title("🏠 Property Finder Tool")

st.write(
    "Extract and clean property listings from a "
    "Property Finder search page."
)

st.info(
    "Paste a public Property Finder search URL below. "
    "The tool extracts information available in the "
    "page response and removes duplicate listings."
)

url = st.text_input(
    "Property Finder search URL",
    placeholder=(
        "https://www.propertyfinder.ae/en/search..."
    )
)

col1, col2 = st.columns([1, 1])

with col1:
    run = st.button(
        "🔎 Analyse listings",
        type="primary",
        use_container_width=True
    )

with col2:
    clear = st.button(
        "Clear",
        use_container_width=True
    )


if clear:
    st.rerun()


if run:

    if not url:
        st.warning(
            "Please enter a Property Finder search URL."
        )
        st.stop()

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        st.error("Please enter a valid URL.")
        st.stop()

    if "propertyfinder" not in parsed.netloc.lower():
        st.warning(
            "This tool is currently designed for "
            "Property Finder URLs."
        )
        st.stop()

    with st.spinner(
        "Loading Property Finder page..."
    ):
        try:
            html, status = fetch_page(url)

        except requests.RequestException as e:
            st.error(
                "The Property Finder page could not be loaded."
            )

            st.code(str(e))

            st.stop()

    st.write(
        f"HTTP status: **{status}**"
    )

    with st.spinner(
        "Extracting property listings..."
    ):
        raw_listings = extract_listings(
            html,
            url
        )

    unique_listings, duplicate_count = (
        deduplicate_listings(
            raw_listings
        )
    )

    # -----------------------------------------------------
    # METRICS
    # -----------------------------------------------------

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Listings found",
        len(raw_listings)
    )

    m2.metric(
        "Unique listings",
        len(unique_listings)
    )

    m3.metric(
        "Duplicates removed",
        duplicate_count
    )

    if not unique_listings:
        st.warning(
            "No structured listings were detected "
            "in the page response."
        )

        st.write(
            "This usually means Property Finder is "
            "loading the listings dynamically. "
            "In that case we will connect the tool "
            "to the actual search request/API in the "
            "next version rather than bypassing "
            "the website's protection."
        )

        st.stop()

    # -----------------------------------------------------
    # DATAFRAME
    # -----------------------------------------------------

    df = pd.DataFrame(
        unique_listings
    )

    display_columns = [
        "id",
        "reference",
        "title",
        "property_type",
        "community",
        "bedrooms",
        "bathrooms",
        "area",
        "price",
        "url",
    ]

    display_columns = [
        c for c in display_columns
        if c in df.columns
    ]

    st.subheader(
        f"Results ({len(df)})"
    )

    st.dataframe(
        df[display_columns],
        use_container_width=True,
        hide_index=True
    )

    # -----------------------------------------------------
    # DOWNLOAD
    # -----------------------------------------------------

    csv = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        label="⬇️ Download CSV",
        data=csv,
        file_name="propertyfinder_listings.csv",
        mime="text/csv",
        use_container_width=True
    )

    # -----------------------------------------------------
    # DETAILS
    # -----------------------------------------------------

    st.subheader("Listing details")

    for index, listing in enumerate(
        unique_listings,
        start=1
    ):

        title = (
            listing.get("title")
            or listing.get("reference")
            or f"Listing {index}"
        )

        with st.expander(
            f"{index}. {title}"
        ):

            left, right = st.columns(
                [2, 1]
            )

            with left:

                if listing.get("description"):
                    st.write(
                        listing["description"]
                    )

                st.write(
                    f"**Community:** "
                    f"{listing.get('community', '-')}"
                )

                st.write(
                    f"**Type:** "
                    f"{listing.get('property_type', '-')}"
                )

                st.write(
                    f"**Bedrooms:** "
                    f"{listing.get('bedrooms', '-')}"
                )

                st.write(
                    f"**Bathrooms:** "
                    f"{listing.get('bathrooms', '-')}"
                )

                st.write(
                    f"**Area:** "
                    f"{listing.get('area', '-')}"
                )

                st.write(
                    f"**Price:** "
                    f"{listing.get('price', '-')}"
                )

                st.write(
                    f"**Reference:** "
                    f"{listing.get('reference', '-')}"
                )

                if listing.get("url"):
                    st.link_button(
                        "Open listing",
                        listing["url"]
                    )

            with right:

                if listing.get("image"):
                    st.image(
                        listing["image"],
                        use_container_width=True
                    )
