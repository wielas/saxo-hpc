import logging
import time
from random import randint

import pandas as pd

from database import create_session, Book
from scraping import query_saxo_with_title_return_search_page, \
    find_book_by_title_in_search_results_return_book_url, get_book_details_html_with_paper_book_check_no_js, \
    save_book_details_to_database_no_recommendations
from utils import normalize_and_translate_text, extract_book_details_dict_no_js, TOP10K, URL, FAUST, \
    TITLE_NORMALIZED, AUTHOR_NORMALIZED, TITLE_ORIGINAL, AUTHOR_ORIGINAL

logging.basicConfig(filename='data/app_errors.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')
logging.info("Starting the scraping process")


def read_input_csv(file_path):
    """Read the CSV file to get the list of tuples (book_title, book_author) and return it as a list"""
    df = pd.read_csv(file_path, encoding="ISO-8859-1")
    df["book_author"] = df["book_author"].fillna('')
    df['normalized_title'] = df['book_title'].apply(normalize_and_translate_text)
    df['normalized_author'] = df['book_author'].apply(normalize_and_translate_text)

    book_info = list(
        zip(df["book_title"], df["normalized_title"], df["book_author"], df["normalized_author"], df["faust_number"],
            df["isbn_scraped"], df['top10k']))
    return book_info


def is_book_scraped_top10k(session, faust):
    """Check if the book is already in the database based on top10k value"""
    return session.query(Book).filter(Book.faust == faust).first()


def scrape_books_top10k_only_no_recommendations():
    input_csv = "data/top_10k_books_numbered_no_repeats.csv"  # ensure proper encoding ISO-8859-1

    book_info = read_input_csv(input_csv)
    session = create_session()

    for i, (title, normal_title, author, normal_author, faust, isbn_scraped, top10k) in enumerate(book_info):
        if is_book_scraped_top10k(session, faust):
            print(f"Book {i + 1} (top10k {top10k}, faust {faust}) is already in the database")
            continue

        print(f"Scraping book {i + 1} (top10k {top10k}) out of {len(book_info)}")

        # normalize the strings
        if not title:
            logging.critical(f"Title is missing for book {i + 1} ABORTING")
            continue

        # get the search page html
        search_page_html = query_saxo_with_title_return_search_page(normal_title)
        if search_page_html is None:  # handled in the function
            continue
        time.sleep(randint(1, 2))

        # get the book page url
        book_page_url = find_book_by_title_in_search_results_return_book_url(search_page_html, normal_author,
                                                                             normal_title)
        if not book_page_url:  # handled in the function
            continue

        # get the book page html (no JS content)
        book_page_html = get_book_details_html_with_paper_book_check_no_js(book_page_url, session)
        if not book_page_html:  # handled in the function
            continue
        time.sleep(randint(1, 2))

        # get the book details
        book_details_dict = extract_book_details_dict_no_js(book_page_html)
        book_details_dict[TITLE_NORMALIZED] = normal_title
        book_details_dict[TITLE_ORIGINAL] = title
        book_details_dict[AUTHOR_NORMALIZED] = normal_author
        book_details_dict[AUTHOR_ORIGINAL] = author
        book_details_dict[FAUST] = faust
        book_details_dict[TOP10K] = top10k
        book_details_dict[URL] = book_page_url

        # print(book_details_dict)
        save_book_details_to_database_no_recommendations(book_details_dict, session)


if __name__ == '__main__':
    scrape_books_top10k_only_no_recommendations()
