import logging
import json
import logging
import time
import traceback

import requests
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from database import Book, Author
from utils import translate_danish_to_english, is_book_correct, \
    extract_book_details_dict, ISBN, TITLE, PAGE_COUNT, PUBLISHED_DATE, PUBLISHER, FORMAT, NUM_OF_RATINGS, RATING, \
    DESCRIPTION, TOP10K, AUTHORS, RECOMMENDATIONS, default_book_dict_with_isbn


def query_saxo_with_title_return_search_page(title):
    """Search for the book on Saxo.com """
    search_url = f"https://www.saxo.com/dk/products/search?query={title.replace(' ', '+')}"
    response = requests.get(search_url)

    if response.status_code == 200:
        return response.text

    else:
        logging.exception(
            f"Failed to fetch search results from Saxo.com for {title}. Status code: {response.status_code} ABORTING")
        return None


def is_query_redirecting_to_book_page(response):
    return 'search?query' not in response.url


def query_saxo_with_isbn_return_book_page_url(isbn):
    """Search for the book on Saxo.com """
    search_url = f"https://www.saxo.com/dk/products/search?query={isbn}"
    response = requests.get(search_url)

    if response.status_code == 200 and is_query_redirecting_to_book_page(response):
        return response.url

    elif response.status_code == 200:  # if the page returns the search page and doesnt redirect to the single entry
        return find_book_by_isbn_in_search_results_return_book_url(response.text, isbn)

    else:
        logging.exception(
            f"Failed to fetch search results from Saxo.com for {isbn}. Status code: {response.status_code}")
        return None


def find_book_by_title_in_search_results_return_book_url(html_content_search_page, author=None, title=None):
    try:
        soup_search_page = BeautifulSoup(html_content_search_page, "html.parser")
        for book in soup_search_page.find_all("div", class_="product-list-teaser"):
            book_parsed = translate_danish_to_english(book.find("a").get("data-val"))
            book_parsed = json.loads(book_parsed)
            print(book_parsed)

            # verify that the book matches the search criteria (author and paperbook)
            if 'Authors' in book_parsed and 'Work' in book_parsed:
                if is_book_correct(author, book_parsed):
                    return book_parsed["Url"]

        logging.info(
            f"Failed to find the book in the search results. Title: {title}, Author: {author}, Book details: {book_parsed} SAVING DEFAULT")
        return 'N/A'

    except:
        logging.error(f"Failed to parse the search results. Title: {title}, Author: {author} ABORTING")
        return False


def find_book_by_isbn_in_search_results_return_book_url(html_content_search_page, isbn):
    try:
        book_parsed = ""
        soup_search_page = BeautifulSoup(html_content_search_page, "html.parser")
        for book in soup_search_page.find_all("div", class_="product-list-teaser"):
            book_parsed = translate_danish_to_english(book.find("a").get("data-val"))
            book_parsed = json.loads(book_parsed)
            print(book_parsed)

            # verify that the book matches the search criteria isbn
            if 'Id' in book_parsed and book_parsed['Id'] == isbn:
                return book_parsed["Url"]

        logging.info(
            f"Failed to find the book in the search results. ISBN: {isbn}, Book details: {book_parsed} SAVING DEFAULT")
        return 'N/A'

    except:
        logging.error(f"Failed to parse the search results. ISBN: {isbn} ABORTING")
        return False


def if_paperbook_option_exists_return_new_url(html_content):
    """ Check if there exists a variant of the book that's a paperbook and if so -- return its link"""
    soup = BeautifulSoup(html_content, "html.parser")
    product_variant_div = soup.find("div", class_="product-variant")

    if product_variant_div:
        # Check if the current page is a paperbook
        active_book_link = product_variant_div.find("a", class_="active icon-book")
        if active_book_link:
            return None

        # If not found, try to find a class 'icon-book'
        book_link = product_variant_div.find("a", class_="icon-book")
        if book_link:
            return "https://www.saxo.com" + book_link.get("href")

    return None


def create_browser_and_wait_for_book_details_page_load(book_detail_page_url):
    """Create a browser and wait for the page to load, then return the page source"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    with Chrome(options=chrome_options) as browser:
        browser.get(book_detail_page_url)
        print(browser.current_url)
        try:
            WebDriverWait(browser, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            WebDriverWait(browser, 30).until(EC.presence_of_element_located((By.CLASS_NAME, "book-slick-slider")))

            # check if paperbook version of the book exists if so -- reiterate
            new_url = if_paperbook_option_exists_return_new_url(browser.page_source)
            if new_url is None:
                html = browser.page_source
            else:
                return create_browser_and_wait_for_book_details_page_load(new_url)

        except TimeoutException:
            print('kurdefiks')
            logging.info(f"Failed to load the page. URL: {book_detail_page_url} SAVING DEFAULT")
            return None

    return html


# SAVING THE BOOK TO THE DATABASE ############################


def save_book_details_to_database(book_details, session, parent=None):
    """Save or update book details in the database."""
    try:
        book = get_book_by_isbn(session, book_details[ISBN])
        if book is None:
            book = create_new_book(book_details)
            session.add(book)
            session.flush()

            link_authors_to_book(book, book_details[AUTHORS], session)

        if parent:
            parent.recommendations.append(book)

        if book_details[TOP10K] != 0:  # if book is in the top10k list, then scrape its recommendations too
            book.top10k = book_details[TOP10K]
            session.flush()
            save_recommended_books(book, book_details[RECOMMENDATIONS], session)

        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Error saving details for '{book_details[TITLE]}', ISBN: {book_details[ISBN]}", e)


def get_book_by_isbn(session, isbn):
    return session.query(Book).filter_by(isbn=isbn).first()


def create_new_book(book_details):
    return Book(
        isbn=book_details[ISBN],
        title=book_details[TITLE],
        page_count=book_details[PAGE_COUNT],
        published_date=book_details[PUBLISHED_DATE],
        publisher=book_details[PUBLISHER],
        format=book_details[FORMAT],
        num_of_ratings=int(book_details[NUM_OF_RATINGS]),
        rating=book_details[RATING],
        description=book_details[DESCRIPTION],
        top10k=book_details[TOP10K]
    )


def get_or_create_book(session, book_details):
    """Retrieve a book by ISBN or create a new one if not found."""
    book = session.query(Book).filter_by(isbn=book_details[ISBN]).first()
    if not book:
        book = create_new_book(book_details)
        session.add(book)
        session.flush()
    return book


def link_authors_to_book(book, authors, session):
    for author_name in authors:
        author = session.query(Author).filter_by(name=author_name).first()
        if not author:
            author = Author(name=author_name)
            session.add(author)
        book.authors.append(author)


def save_recommended_books(parent_book, recommended_isbns, session):
    for recommended_isbn in recommended_isbns:
        existing_recommended_book = get_book_by_isbn(session, recommended_isbn)
        if existing_recommended_book:
            parent_book.recommendations.append(existing_recommended_book)
            continue
        scrape_and_save_recommended_book(parent_book, recommended_isbn, session)
        time.sleep(1)


def scrape_and_save_recommended_book(parent_book, book_isbn, session):  # todo optimize
    """Scrape the details of a recommended book if it does not exist in the database"""
    try:
        book_page_url = query_saxo_with_isbn_return_book_page_url(book_isbn)
        if book_page_url == 'N/A':
            logging.info(
                f"Book {book_isbn} recommended by {parent_book.isbn} not found in the search results SAVING DEFAULT")
            default_book_dict = default_book_dict_with_isbn(book_isbn)
            save_book_details_to_database(default_book_dict, session, parent=parent_book)
            return
        # get the fully loaded book page html
        book_page_html = create_browser_and_wait_for_book_details_page_load(book_page_url)
        if book_page_html is None:
            logging.info(f"Book {book_isbn} recommended by {parent_book.isbn} failed to load page SAVING DEFAULT")
            default_book_dict = default_book_dict_with_isbn(book_isbn)
            save_book_details_to_database(default_book_dict, session, parent=parent_book)
            return

        book_details_dict = extract_book_details_dict(book_page_html)
        book_details_dict[TOP10K] = 0
        save_book_details_to_database(book_details_dict, session, parent=parent_book)

    except Exception as e:
        logging.error(f"Scraping the recommended book with ISBN failed {book_isbn}: {e} ABORTING")
        logging.error(traceback.format_exc())
