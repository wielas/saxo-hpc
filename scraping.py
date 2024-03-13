import logging
import json
import logging
import time
import traceback
from enum import Enum

import requests
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from database import Book, Author
from utils import translate_danish_to_english, is_book_correct, \
    extract_book_details_dict, ISBN, TITLE, PAGE_COUNT, PUBLISHED_DATE, PUBLISHER, FORMAT, NUM_OF_RATINGS, RATING, \
    DESCRIPTION, TOP10K, AUTHORS, RECOMMENDATIONS, default_book_dict_with_isbn, URL, LoadStatus


def query_saxo_with_title_return_search_page(title, proxy, no_of_proxy):
    """Search for the book on Saxo.com """
    search_url = f"https://www.saxo.com/dk/products/search?query={title.replace(' ', '+')}"
    proxies = {"http": proxy, "https": proxy}

    try:
        response = requests.get(search_url, proxies=proxies)

        if response.status_code == 200:
            return response.text

        else:
            logging.exception(
                f"Failed to fetch search results from Saxo.com for {title}. Status code: {response.status_code} ABORTING")
            return None

    except requests.exceptions.ProxyError:
        logging.error(f"Proxy Error with proxy {proxy}, {no_of_proxy} in query_saxo_with_title_return_search_page")
    except requests.exceptions.ConnectTimeout:
        logging.error(
            f"Connection timeout with proxy {proxy}, {no_of_proxy} in query_saxo_with_title_return_search_page")


def is_query_redirecting_to_book_page(response):
    return 'search?query' not in response.url


def query_saxo_with_isbn_return_book_page_url(isbn, proxy, no_of_proxy):
    """Search for the book on Saxo.com """
    search_url = f"https://www.saxo.com/dk/products/search?query={isbn}"
    try:
        response = requests.get(search_url)

        if response.status_code == 200 and is_query_redirecting_to_book_page(response):
            return response.url

        elif response.status_code == 200:  # if the page returns the search page and doesnt redirect to the single entry
            return find_book_by_isbn_in_search_results_return_book_url(response.text, isbn)

        else:
            logging.exception(
                f"Failed to fetch search results from Saxo.com for {isbn}. Status code: {response.status_code}")
            return None
    except requests.exceptions.ProxyError:
        logging.error(f"Proxy Error with proxy {proxy}, {no_of_proxy} in query_saxo_with_isbn_return_book_page_url")
    except requests.exceptions.ConnectTimeout:
        logging.error(
            f"Connection timeout with proxy {proxy}, {no_of_proxy} in query_saxo_with_isbn_return_book_page_url")


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
        logging.error(f"Failed to parse the search results. Title: {title}, Author: {author}")
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


def is_book_scraped_url(session, url):
    return session.query(Book).filter(Book.url == url).first()


def create_browser_and_wait_for_book_details_page_load(book_detail_page_url, session, proxy, no_of_proxy):
    """Create a browser and wait for the page to load, then return the page source"""
    selenium_proxy = Proxy({
        'proxyType': ProxyType.MANUAL,
        'httpProxy': proxy,
        'ftpProxy': proxy,
        'sslProxy': proxy,
        'noProxy': ''
    })

    chrome_options = Options()
    selenium_proxy.add_to_capabilities(chrome_options.capabilities)

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
                return create_browser_and_wait_for_book_details_page_load(new_url, session, proxy, no_of_proxy)

            # if book is already scraped, return False with html to still scrape its recommendations
            if is_book_scraped_url(session, browser.current_url):
                print(f"Book {browser.current_url} already scraped")
                return (LoadStatus.EXISTING, html)

        except TimeoutException:
            print('kurdefiks')
            logging.info(f"Failed to load the page. URL: {book_detail_page_url} SAVING DEFAULT")
            return (LoadStatus.ERROR, None)

    # otherwise, return the html
    return (LoadStatus.NEW, html)


# SAVING THE BOOK TO THE DATABASE ############################

def save_book_details_to_database(book_details, session, proxy, no_of_proxy, parent=None):
    """Save or update book details in the database."""
    try:
        book = get_book_by_isbn(session, book_details[ISBN])
        if book is None:
            book = create_new_book(book_details)
            session.add(book)
            session.flush()

            link_authors_to_book(book, book_details[AUTHORS], session)

        if parent:  # this statement essentially means that the book is a second-layer recommended book
            link_children_book_recommendations(book, book_details[RECOMMENDATIONS], session)

            if book not in parent.recommendations:
                parent.recommendations.append(book)
                session.flush()

        if book_details[TOP10K] != 0:  # this means that the book is in the first-layer list
            # if book is in the top10k list, then scrape its recommendations too
            book.top10k = book_details[TOP10K]
            session.flush()
            save_recommended_books(book, book_details[RECOMMENDATIONS], session, proxy, no_of_proxy)

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
        url=book_details[URL],
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


def link_children_book_recommendations(parent_book, recommended_books, session):
    for recommended_book in recommended_books:
        recommended_book = get_book_by_isbn(session, recommended_book)
        if recommended_book and recommended_book not in parent_book.recommendations:
            parent_book.recommendations.append(recommended_book)
            session.flush()


def link_authors_to_book(book, authors, session):
    for author_name in authors:
        author = session.query(Author).filter_by(name=author_name).first()
        if not author:
            author = Author(name=author_name)
            session.add(author)
        if not author in book.authors:
            book.authors.append(author)


def save_recommended_books(parent_book, recommended_isbns, session, proxy, no_of_proxy):
    """Save the recommended books to the database if they don't exist yet"""
    for recommended_isbn in recommended_isbns:
        # check if the recommended book is already in the database
        existing_recommended_book = get_book_by_isbn(session, recommended_isbn)
        if existing_recommended_book and existing_recommended_book not in parent_book.recommendations:
            parent_book.recommendations.append(existing_recommended_book)
            continue

        # if not, scrape the details and save it
        scrape_and_save_recommended_book(parent_book, recommended_isbn, session, proxy, no_of_proxy)
        time.sleep(1)


def scrape_and_save_recommended_book(parent_book, book_isbn, session, proxy, no_of_proxy):  # todo optimize
    """Scrape the details of a recommended book if it does not exist in the database"""
    try:
        book_page_url = query_saxo_with_isbn_return_book_page_url(book_isbn, proxy, no_of_proxy)
        if book_page_url == 'N/A':
            logging.info(
                f"Book {book_isbn} recommended by {parent_book.isbn} not found in the search results SAVING DEFAULT")
            default_book_dict = default_book_dict_with_isbn(book_isbn)
            save_book_details_to_database(default_book_dict, session, proxy, no_of_proxy, parent=parent_book)
            return

        # get the fully loaded book page html
        (status, book_page_html) = create_browser_and_wait_for_book_details_page_load(book_page_url, session, proxy, no_of_proxy)
        if status == LoadStatus.ERROR:
            logging.info(f"Book {book_isbn} recommended by {parent_book.isbn} failed to load page SAVING DEFAULT")
            default_book_dict = default_book_dict_with_isbn(book_isbn)
            save_book_details_to_database(default_book_dict, session, proxy, no_of_proxy, parent=parent_book)
            return
        elif status == LoadStatus.EXISTING:
            logging.info(f"The book {book_isbn} already exists in the db failed SKIPPING")
            return
        else:
            book_details_dict = extract_book_details_dict(book_page_html)
            book_details_dict[TOP10K] = 0
            book_details_dict[URL] = book_page_url
            save_book_details_to_database(book_details_dict, session, proxy, no_of_proxy, parent=parent_book)

    except Exception as e:
        logging.error(f"Scraping the recommended book with ISBN failed {book_isbn}: {e} ABORTING")
