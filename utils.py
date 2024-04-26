import logging
import re
from difflib import SequenceMatcher

import unicodedata
from enum import Enum

from bs4 import BeautifulSoup

# for mapping the keys extracted from the book page to the keys in the database
KEY_MAPPINGS = {
    "Sprog": "Language",
    "Sidetal": "PageCount",
    "Udgivelsesdato": "PublishedDate",
    "ISBN13": "ISBN",
    "Forlag": "Publisher",
    "Format": "Format",
}

# for saving to db
FAUST = "Fausts"
ISBN = "ISBN"
CSV_ISBN = "CSV_ISBN"
TITLE = "Title"
TITLE_NORMALIZED = "TitleNormalized"
TITLE_ORIGINAL = "TitleOriginal"
AUTHOR_NORMALIZED = "AuthorNormalized"
AUTHOR_ORIGINAL = "AuthorOriginal"
PAGE_COUNT = "PageCount"
PUBLISHED_DATE = "PublishedDate"
PUBLISHER = "Publisher"
FORMAT = "Format"
NUM_OF_RATINGS = "NumOfRatings"
RATING = "Rating"
DESCRIPTION = "Description"
TOP10K = "Top10k"
AUDIENCE = "Audience"
GENRE = "Genre"
LOANS = "Loans"
AUTHORS = "Authors"
URL = "Url"
RECOMMENDATIONS = "Recommendations"

# for creating a default book entry
BOOK_NOT_AVAILABLE = {ISBN: 'x',
                      PAGE_COUNT: 0,
                      PUBLISHED_DATE: 'N/A',
                      PUBLISHER: 'N/A',
                      FORMAT: 'N/A',
                      TITLE: 'N/A',
                      AUTHORS: [],
                      NUM_OF_RATINGS: -1,
                      RATING: -1,
                      DESCRIPTION: "N/A",
                      RECOMMENDATIONS: [],
                      URL: 'N/A',
                      TOP10K: 0}


class LoadStatus(Enum):
    NEW = "new"
    EXISTING = "existing"
    ERROR = "error"


def default_book_dict_with_title_author(title, authors, top10k):
    default_book = BOOK_NOT_AVAILABLE.copy()
    default_book[ISBN] = top10k  # TODO REMEMBER THIS CASE
    default_book[TITLE] = title
    default_book[AUTHORS] = list(authors)
    default_book[TOP10K] = top10k
    return default_book


def default_book_dict_with_isbn(isbn):
    default_book = BOOK_NOT_AVAILABLE.copy()
    default_book[ISBN] = isbn
    return default_book


########## new code ##########
def normalize_and_translate_text(text):
    # Normalize text to lowercase and remove non-alphanumeric characters except spaces
    text = translate_danish_to_english(text)
    return ''.join(char.lower() for char in text if char.isalnum() or char.isspace())


def similar(a, b):
    # Calculate normalized Levenshtein distance and return similarity score
    return SequenceMatcher(None, a, b).ratio()


def match_titles(title1, title2):
    # Check if the titles are similar enough (edit distance <= 1)
    return similar(title1, title2) > 0.85


def match_authors(author1, author2):
    # Split the author names into parts and check for first name and at least one other name match
    names1 = set(normalize_and_translate_text(author1).split())
    names2 = set(normalize_and_translate_text(author2).split())
    if len(names1) == 0 or len(names2) == 0:
        return False
    # Check if least one name match
    return len(names1.intersection(names2)) >= 1


def check_match(current_row_title, web_title, current_row_author, web_author):
    # Normalize data
    current_row_title_normalized = normalize_and_translate_text(current_row_title)
    current_row_author_normalized = normalize_and_translate_text(current_row_author)
    web_title_normalized = normalize_and_translate_text(web_title)
    web_author_normalized = normalize_and_translate_text(web_author)

    # Check matches
    if match_titles(current_row_title_normalized, web_title_normalized) and \
            match_authors(current_row_author_normalized, web_author_normalized):
        return True
    else:
        return False


########## ///////////new code ##########


def normalize_special_characters(text):
    # Normalize the text by separating characters and their diacritical marks (e.g., 'á' becomes 'a' + '´')
    normalized_text = unicodedata.normalize('NFD', text)
    normalized_text = ''.join(
        char for char in normalized_text
        if unicodedata.category(char) != 'Mn'
        and (ord(char) < 128 or char == ',' or char == '*' or char == '-')
    )

    return normalized_text


def translate_danish_to_english(text):
    translations = {
        'æ': 'ae',
        'ø': 'oe',
        'å': 'aa',
        'Æ': 'Ae',
        'Ø': 'Oe',
        'Å': 'Aa'
    }

    for danish_char, english_char in translations.items():
        text = text.replace(danish_char, english_char)

    return text


# hidden og code
# def is_book_correct(authors_local, book_parsed):
#     """Parse the first author and compare it to the extracted authors. Return True if the names match."""
#     authors_extracted = book_parsed["Authors"]
#     work = book_parsed["Work"].lower()
#     id = book_parsed["Id"]
#
#     if authors_local is None:
#         return id.isdigit() and work != 'brugt bog'
#     authors_local = authors_local.lower().replace('"', "")
#     first_author_local = authors_local.split(',')[0] if ',' in authors_local else authors_local
#     first_author_local_normalized = normalize_author_string(first_author_local)
#
#     authors_extracted_normalized = [normalize_author_string(author.lower()) for author in list(authors_extracted)]
#     return first_author_local_normalized in authors_extracted_normalized and id.isdigit() and work != 'brugt bog'
#

# EXTRACT THE DETAILS FROM THE BOOK PAGE ########################################

# def extract_book_details_dict(book_page_html):
#     """Scrape and structure the book's details from its HTML page content."""
#     soup = BeautifulSoup(book_page_html, "html.parser")
#     title = extract_title(soup)
#     authors = extract_authors(soup)
#     details = extract_details(soup)
#     product_description = extract_description(soup)
#     rating, num_of_reviews = extract_reviews(soup)
#     recommendations = extract_recommendations_list(book_page_html)
#
#     # Combine all extracted details into a single dictionary
#     book_details = {**details, TITLE: title, AUTHORS: authors,
#                     NUM_OF_RATINGS: num_of_reviews, RATING: rating, DESCRIPTION: product_description,
#                     RECOMMENDATIONS: recommendations}
#     return book_details


def extract_book_rating_and_recommendations(book_page_html, top10k_isbn_list):
    """Scrape and structure the book's details from its HTML page content."""
    soup = BeautifulSoup(book_page_html, "html.parser")
    rating, num_of_reviews = extract_reviews(soup)
    recommendations = extract_recommendations_list(book_page_html, top10k_isbn_list)

    # Combine all extracted details into a single dictionary
    book_details = {NUM_OF_RATINGS: num_of_reviews, RATING: rating,
                    RECOMMENDATIONS: recommendations}
    return book_details


def extract_title(soup):
    title = soup.find("h1", class_="text-xl sm:text-l text-800 mb-0").text.strip()
    return normalize_and_translate_text(title)


def extract_authors(soup):
    authors = []
    author_tags = soup.find('div', class_='text-s product-autor').find_all('a', class_='link link--black')
    authors = [normalize_and_translate_text(tag.get_text(strip=True)) for tag in author_tags if tag != "&"]
    return authors


def extract_details(soup):
    details_section = soup.find("ul", class_="description-dot-list")
    return details_to_dict(details_section)


def extract_description(soup):
    description_tag = soup.find("p", class_="mb-0")
    return description_tag.text.strip() if description_tag else "Description Not Available"


def extract_reviews(soup):
    reviews_container = soup.find("div", class_="product-rating")
    if not reviews_container:
        return 0, 0  # return default values if the container not found

    rating = extract_rating(reviews_container)
    num_of_reviews = extract_review_count(reviews_container)
    return rating, num_of_reviews


def extract_rating(reviews_container):
    rating_tag = reviews_container.find('span', class_="text-l text-800")
    if rating_tag:
        rating_str = rating_tag.text.strip().replace(",", ".")
        try:
            return float(rating_str)
        except ValueError:
            logging.error(f"Failed to convert rating '{rating_str}' to float.")
    return 0  # Return default if rating is not found or conversion fails


def extract_review_count(reviews_container):
    review_count_tag = reviews_container.find('span', class_="text-s")
    if review_count_tag:
        review_count_str = review_count_tag.text.strip().split(" ")[0].replace("(", "").replace(")", "")
        try:
            return int(review_count_str)
        except ValueError:
            logging.error(f"Failed to convert review count '{review_count_str}' to int.")
    return 0  # default if review count is not found or conversion fails


def details_to_dict(details_section):
    """Convert the details section to a dictionary, with key mappings and type conversions."""
    book_details = {}
    for li in details_section.find_all('li'):
        key, value = extract_detail(li)
        if key in KEY_MAPPINGS:
            mapped_key = KEY_MAPPINGS[key]
            book_details[mapped_key] = convert_page_count(mapped_key, value)

    # ensure 'PageCount' exists in book_details
    book_details.setdefault('PageCount', 0)
    return book_details


def extract_detail(list_item):
    """Extract detail key and value from a list item."""
    key_span = list_item.select_one('span.text-700')
    if not key_span:
        return None, None  # Return None if key span is not found

    key = key_span.text.strip()
    key_span.extract()  # Remove the key span to easily extract the remaining text
    value = list_item.text.strip()
    return key, value


def convert_page_count(key, value):
    """Convert detail value based on the key."""
    if key == "PageCount":
        try:
            return int(value)
        except ValueError:
            logging.error(f"Failed to convert page count '{value}' to int.")
            return 0
    return value

def find_h2_tag_with_right_recommendations(soup):
    h2_tag = soup.find('h2', string="Andre købte også")
    if not h2_tag:
        h2_tag = soup.find('h2', string="Andre kiggede også på disse bøger")
    if not h2_tag:
        h2_tag = soup.find('h2', string="Andre kiggede også på")
    if not h2_tag:
        h2_tag = soup.find('h2', string="Lignende bøger i samme genre")
    if not h2_tag:
        h2_tag = soup.find('h2', string="Ofte købt sammen med denne bog")
    if not h2_tag:
        h2_tag = soup.find('h2', string="Populære bøger i samme genre")
        if h2_tag:
            logging.info(f"book {extract_title(soup)} is recommended as popular in the same genre")
    return h2_tag

def extract_recommendations_list(book_page_html, top10k_isbn_list):
    """Scrape the book's recommendations based on its HTML page content."""
    soup = BeautifulSoup(book_page_html, "html.parser")
    recommendations_isbn = []
    recommendations = ''

    h2_tag = find_h2_tag_with_right_recommendations(soup)

    # Check if the recommendatons come from others also bought section
    if h2_tag and h2_tag.find_next_sibling(class_="book-slick-slider"):
        recommendations = h2_tag.find_next_sibling(class_="book-slick-slider")

    if recommendations:
        cover_containers = recommendations.find_all("div", class_=lambda e: e.startswith('new-teaser') if e else False)
        for cover in cover_containers:
            isbn = cover.find("a", class_="cover-container").get('data-product-identifier')
            if isbn and isbn in top10k_isbn_list:
                recommendations_isbn.append(isbn)
            else:
                logging.error("Failed to extract a recommendation ISBN from the book page.")
    return recommendations_isbn


