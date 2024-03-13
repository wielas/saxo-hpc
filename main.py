import logging
import math

import pandas as pd

from database import Book, create_session
from scraping import query_saxo_with_title_return_search_page, \
    find_book_by_title_in_search_results_return_book_url, create_browser_and_wait_for_book_details_page_load, \
    save_book_details_to_database
from utils import normalize_author_string, normalize_book_title_string, extract_book_details_dict, TOP10K, \
    default_book_dict_with_title_author, URL, ISBN, LoadStatus

logging.basicConfig(filename='data/app_errors.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')
logging.info("Starting the scraping process")


# todo add a check for book 34 with url error

def read_input_csv(file_path):
    """Read the CSV file to get the list of tuples (book_title, book_author) and return it as a list"""
    df = pd.read_csv(file_path, encoding="ISO-8859-1")
    df["book_author"] = df["book_author"].fillna('')
    book_info = list(zip(df["book_title"], df["book_author"]))
    return book_info


def is_book_scraped_top10k(session, i):
    """Check if the book is already in the database based on top10k value"""
    return session.query(Book).filter(Book.top10k == i).first()


def normalize_title_and_author(title, author):
    title = normalize_book_title_string(title)

    if author:
        author = normalize_author_string(author)
    else:
        author = ""
        logging.info(f"Author is missing for book {i + 1}: {title}")

    return title, author


def save_default_book(title, author, i, session):
    default_book_dict = default_book_dict_with_title_author(title, author, i + 1)
    save_book_details_to_database(default_book_dict, session)


if __name__ == "__main__":

    input_csv = "data/top_10k_books.csv"

    book_info = read_input_csv(input_csv)
    session = create_session()

    for i, (title, author) in enumerate(book_info):
        if is_book_scraped_top10k(session, i + 1):
            print(f"Book {i + 1} already scraped")
            continue

        print(f"Scraping book {i + 1} out of {len(book_info)}")
        # normalize the strings
        if not title:
            logging.critical(f"Title is missing for book {i + 1} ABORTING")
            continue
        title, author = normalize_title_and_author(title, author)

        # get the search page html
        search_page_html = query_saxo_with_title_return_search_page(title)
        if search_page_html is None:
            continue

        # get the book page url
        book_page_url = find_book_by_title_in_search_results_return_book_url(search_page_html, author, title)
        if book_page_url == 'N/A':
            logging.info(f"Book {i + 1} not found in the search results SAVING DEFAULT")
            save_default_book(title, author, i, session)
            continue

        if book_page_url is False:
            logging.info(f"Getting results for book {i + 1}, Title: {title}, Author: {author} failed SAVING DEFAULT")
            save_default_book(title, author, i, session)
            continue

        # get the fully loaded book page html
        (status, book_page_html) = create_browser_and_wait_for_book_details_page_load(book_page_url, session)
        if status is LoadStatus.ERROR:
            logging.error(f"Failed to get the book page html for book {i + 1}: {title}, {author} SAVING DEFAULT")
            save_default_book(title, author, i, session)
            continue
        # if same book already exists in db
        if status is LoadStatus.EXISTING:
            book_details_dict = extract_book_details_dict(book_page_html)
            book_details_dict[TOP10K] = i + 1
            book_details_dict[URL] = book_page_url
            book_details_dict[ISBN] = book_details_dict[ISBN] + f"_{i + 1}"
            logging.info(f"Book already exists {i + 1}:{book_details_dict[ISBN]}, {title}, {author} ADDING _TOP10K to ISBN")
            save_book_details_to_database(book_details_dict, session)
            continue
        # extract the book details normally
        else:
            book_details_dict = extract_book_details_dict(book_page_html)
            book_details_dict[TOP10K] = i + 1
            book_details_dict[URL] = book_page_url
            save_book_details_to_database(book_details_dict, session)
