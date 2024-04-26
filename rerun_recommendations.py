import logging
import time
from random import randint

import pandas as pd

from database import create_session, Book
from scraping import query_saxo_with_title_return_search_page, \
    find_book_by_title_in_search_results_return_book_url, get_book_details_html_with_paper_book_check_no_js, \
    save_book_details_to_database_no_recommendations, create_browser_for_recommendation_scrape, \
    save_book_recommendations_and_reviews_to_database
from utils import normalize_and_translate_text, extract_book_rating_and_recommendations, TOP10K, URL, FAUST, \
    TITLE_NORMALIZED, AUTHOR_NORMALIZED, TITLE_ORIGINAL, AUTHOR_ORIGINAL, AUDIENCE, GENRE, LOANS, CSV_ISBN, \
    ISBN, extract_recommendations_list

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


def is_book_scraped_top10k(session, title):
    """Check if the book is already in the database"""
    return session.query(Book).filter(Book.title_original == title).first()


def get_top10k_books_ordered_from_db(session):
    return session.query(Book).order_by(Book.top10k.asc()).all()


def get_top10k_isbn_from_db(session):
    isbn_list = session.query(Book.isbn).all()
    return [isbn[0] for isbn in isbn_list if isbn[0] is not None]


def scrape_recommendations_top10k_only():
    input_csv = "data/top10k_book_metadata_v4.csv"  # ensure proper encoding ISO-8859-1

    session = create_session()
    top10k_books = get_top10k_books_ordered_from_db(session)
    top10k_isbns = get_top10k_isbn_from_db(session)

    for book in top10k_books:
        if book.scraped_recommendations:
            print(f"top10k: {book.top10k} Recommendations already scraped for title: {book.title}, url: {book.url}")
            continue

        if book.recommendations:
            print(f"top10k: {book.top10k} Already has recommendations title: {book.title}, url: {book.url}")
            continue

        print(f"Top10k: {book.top10k} out of: {len(top10k_books)} Title: {book.title_original}, url: {book.url}")
        book_detail_url = book.url
        book_detail_html = create_browser_for_recommendation_scrape(book_detail_url)  # todo add check when kurdefiks

        if not(book_detail_html):
            print(f"Book {book.title} has no recommendations")
            logging.info(f"Book {book.title} has no recommendations")
            continue

        book_details_dict = extract_book_rating_and_recommendations(book_detail_html, top10k_isbns)
        print(book_details_dict)
        save_book_recommendations_and_reviews_to_database(book, book_details_dict, session)


    print("Done. :)")


if __name__ == '__main__':
    scrape_recommendations_top10k_only()
