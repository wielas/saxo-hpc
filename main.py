import logging

import pandas as pd

from database import Book, create_session
from scraping import query_saxo_with_title_return_search_page, \
    find_book_by_title_in_search_results_return_book_url, create_browser_and_wait_for_book_details_page_load, \
    save_book_details_to_database
from utils import normalize_author_string, normalize_book_title_string, extract_book_details_dict, TOP10K, \
    default_book_dict_with_title_author

logging.basicConfig(filename='data/app_errors.log', level=logging.ERROR,
                    format='%(asctime)s:%(levelname)s:%(message)s')


def read_input_csv(file_path):
    """Read the CSV file to get the list of tuples (book_title, book_author) and return it as a list"""
    df = pd.read_csv(file_path, encoding="ISO-8859-1")
    book_info = list(zip(df["book_title"], df["book_author"]))
    return book_info


def is_book_scraped(session, i):
    """Check if the book is already in the database based on top10k value"""
    return session.query(Book).filter(Book.top10k == i).first()


def normalize_title_and_author(title, author):
    title = normalize_book_title_string(title)

    if author:
        author = normalize_author_string(author)
    else:
        author = ""
        logging.error(f"Author is missing for book {i + 1}: {title}")

    return title, author


if __name__ == "__main__":

    input_csv = "data/top_10k_books.csv"

    book_info = read_input_csv(input_csv)
    session = create_session()

    for i, (title, author) in enumerate(book_info):
        print(f"Scraping book {i + 1} out of {len(book_info)}")
        # normalize the strings
        if not title:
            logging.error(f"Title is missing for book {i + 1} ABORTING")
            continue
        title, author = normalize_title_and_author(title, author)

        # get the search page html
        search_page_html = query_saxo_with_title_return_search_page(title)
        if search_page_html is None:
            continue

        # get the book page url
        book_page_url = find_book_by_title_in_search_results_return_book_url(search_page_html, author, title)
        if book_page_url == 'N/A':
            logging.info(f"Book {i + 1} not found in the search results")
            default_book_dict = default_book_dict_with_title_author(title, author, i + 1)
            save_book_details_to_database(default_book_dict, session)
            continue

        # get the fully loaded book page html
        book_page_html = create_browser_and_wait_for_book_details_page_load(book_page_url)
        if book_page_html is None:
            default_book_dict = default_book_dict_with_title_author(title, author, i + 1)
            save_book_details_to_database(default_book_dict, session)
            continue

        # extract the book details
        book_details_dict = extract_book_details_dict(book_page_html)
        book_details_dict[TOP10K] = i + 1
        save_book_details_to_database(book_details_dict, session)
