import logging
import time
from random import randint

import pandas as pd

from database import create_session, Book
from scraping import query_saxo_with_title_return_search_page, \
    find_book_by_title_in_search_results_return_book_url, get_book_details_html_with_paper_book_check_no_js, \
    save_book_details_to_database_no_recommendations
from utils import normalize_and_translate_text, extract_book_details_dict_no_js, TOP10K, URL, FAUST, \
    TITLE_NORMALIZED, AUTHOR_NORMALIZED, TITLE_ORIGINAL, AUTHOR_ORIGINAL, AUDIENCE, GENRE, LOANS, CSV_ISBN, \
    ISBN

logging.basicConfig(filename='data/app_errors.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')
logging.info("Starting the scraping process")


def read_input_csv(file_path):
    """Read the CSV file to get the list of tuples (book_title, book_author) and return it as a list"""
    df = pd.read_csv(file_path, encoding="ISO-8859-1")
    df["isbns"] = df["isbns"].fillna('')
    df["author"] = df["author"].fillna('')
    df['normalized_title'] = df['title'].apply(normalize_and_translate_text)
    df['normalized_author'] = df['author'].apply(normalize_and_translate_text)

    book_info = list(
        zip(df["title"], df["normalized_title"], df["author"], df["normalized_author"], df["faust_numbers"],
            df["isbns"], df["audience"], df["genre"], df["n_loans"], df['top10k']))
    return book_info


def is_book_scraped_title(session, title):
    """Check if the book is already in the database"""
    return session.query(Book).filter(Book.title_original == title).first()

def is_book_scraped_top10k(session, top10k):
    """Check if the book is already in the database"""
    return session.query(Book).filter(Book.top10k == top10k).first()


def scrape_books_top10k_only_no_recommendations():
    input_csv = "data/top10k_book_metadata_v4.csv"  # ensure proper encoding ISO-8859-1

    book_info = read_input_csv(input_csv)
    session = create_session()

    for i, (title, normal_title, author, normal_author, fausts, isbns, audience, genre, loans, top10k) in enumerate(book_info):
        if i < 9730:
            continue

        if is_book_scraped_top10k(session, top10k):
            print(f"Book {i + 1} (top10k {top10k}) is already in the database")
            continue

        if is_book_scraped_title(session, title):
            print(f"Book {i + 1} (title: {title}, normal_title: {normal_title}) is already in the database")
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
        book_details_dict[AUDIENCE] = audience
        book_details_dict[GENRE] = genre
        book_details_dict[LOANS] = loans
        book_details_dict[FAUST] = fausts
        book_details_dict[CSV_ISBN] = isbns
        book_details_dict[TOP10K] = top10k
        book_details_dict[URL] = book_page_url
        print(book_details_dict)

        # print(book_details_dict)
        save_book_details_to_database_no_recommendations(book_details_dict, session)


if __name__ == '__main__':
    scrape_books_top10k_only_no_recommendations()
