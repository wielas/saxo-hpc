import logging
import re

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
ISBN = "ISBN"
TITLE = "Title"
PAGE_COUNT = "PageCount"
PUBLISHED_DATE = "PublishedDate"
PUBLISHER = "Publisher"
FORMAT = "Format"
NUM_OF_RATINGS = "NumOfRatings"
RATING = "Rating"
DESCRIPTION = "Description"
TOP10K = "Top10k"
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
    default_book[ISBN] = top10k
    default_book[TITLE] = title
    default_book[AUTHORS] = list(authors)
    default_book[TOP10K] = top10k
    return default_book


def default_book_dict_with_isbn(isbn):
    default_book = BOOK_NOT_AVAILABLE.copy()
    default_book[ISBN] = isbn
    return default_book


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


def normalize_author_string(name):
    name = translate_danish_to_english(name)
    name = normalize_special_characters(name)

    # Remove common business entity suffixes and punctuation, while keeping commas
    suffixes = ['Ltd', 'Inc', 'Co', 'LLC', 'LLP', 'PLC']
    pattern = r'\b(?:' + '|'.join(suffixes) + r')\.?\b'
    name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    # Remove any parenthesized content
    name = re.sub(r'\(.*?\)', '', name)

    # Remove any remaining punctuation (except for commas) and extra whitespace
    name = re.sub(r'[^\w\s,]', '', name)  # Keep commas by adding them to the character set
    name = re.sub(r'\s+', ' ', name).strip()

    return name.lower()


def normalize_book_title_string(title):
    """ normalize a book title by trimming, converting to lowercase, and removing special characters"""
    title = translate_danish_to_english(title)
    title = normalize_special_characters(title)

    normalized_title = title.strip()
    normalized_title = normalized_title.lower()
    # Remove special characters except for spaces and alphanum
    normalized_title = re.sub(r'[^a-zA-Z0-9\s]', '', normalized_title)

    return normalized_title


def is_book_correct(authors_local, book_parsed):
    """Parse the first author and compare it to the extracted authors. Return True if the names match."""
    authors_extracted = book_parsed["Authors"]
    work = book_parsed["Work"].lower()
    id = book_parsed["Id"]

    if authors_local is None:
        return id.isdigit() and work != 'brugt bog'
    authors_local = authors_local.lower().replace('"', "")
    first_author_local = authors_local.split(',')[0] if ',' in authors_local else authors_local
    first_author_local_normalized = normalize_author_string(first_author_local)

    authors_extracted_normalized = [normalize_author_string(author.lower()) for author in list(authors_extracted)]
    return first_author_local_normalized in authors_extracted_normalized and id.isdigit() and work != 'brugt bog'


# EXTRACT THE DETAILS FROM THE BOOK PAGE ########################################

def extract_book_details_dict(book_page_html):
    """Scrape and structure the book's details from its HTML page content."""
    soup = BeautifulSoup(book_page_html, "html.parser")
    title = extract_title(soup)
    authors = extract_authors(soup)
    details = extract_details(soup)
    product_description = extract_description(soup)
    rating, num_of_reviews = extract_reviews(soup)
    recommendations = extract_recommendations_list(book_page_html)

    # Combine all extracted details into a single dictionary
    book_details = {**details, TITLE: title, AUTHORS: authors,
                    NUM_OF_RATINGS: num_of_reviews, RATING: rating, DESCRIPTION: product_description,
                    RECOMMENDATIONS: recommendations}
    return book_details


def extract_title(soup):
    title = soup.find("h1", class_="text-xl sm:text-l text-800 mb-0").text.strip()
    return normalize_book_title_string(title)


def extract_authors(soup):
    authors = []
    author_tags = soup.find('div', class_='text-s product-autor').find_all('a', class_='link link--black')
    authors = [normalize_author_string(tag.get_text(strip=True)) for tag in author_tags if tag != "&"]
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


def extract_recommendations_list(book_page_html):
    """Scrape the book's recommendations based on its HTML page content."""
    soup = BeautifulSoup(book_page_html, "html.parser")
    recommendations_isbn = []
    recommendations = soup.find("div", id="product-page-banner-container").find("div",
                                                                                class_="book-slick-slider slick-initialized slick-slider")

    if recommendations:
        cover_containers = recommendations.find_all("div", class_=lambda e: e.startswith('new-teaser') if e else False)
        for cover in cover_containers:
            isbn = cover.find("a", class_="cover-container").get('data-product-identifier')
            if isbn:
                recommendations_isbn.append(isbn)
            else:
                logging.error("Failed to extract a recommendation ISBN from the book page.")
    return recommendations_isbn
