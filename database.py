from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

# table for the many-to-many relationship between books and authors
book_author = Table('book_author', Base.metadata,
                    Column('book_faust', String, ForeignKey('book.faust'), primary_key=True),
                    Column('author_name', String, ForeignKey('author.name'), primary_key=True)
                    )

# table for the many-to-many relationship between books and their recommendations
recommendation_table = Table('recommendation', Base.metadata,
                             Column('book_faust', ForeignKey('book.faust'), primary_key=True),
                             Column('recommended_faust', ForeignKey('book.faust'), primary_key=True)
                             )


class Book(Base):
    __tablename__ = 'book'

    faust = Column(Integer, primary_key=True)
    isbn = Column(String)
    title = Column(String, nullable=False)
    title_original = Column(String)
    title_normalized = Column(String)
    authors_original = Column(String)
    authors_normalized = Column(String)
    page_count = Column(Integer)
    published_date = Column(String)
    publisher = Column(String)
    format = Column(String)
    num_of_ratings = Column(Integer)
    rating = Column(String)
    description = Column(Text)
    url = Column(String)
    top10k = Column(Integer, default=0)

    authors = relationship('Author', secondary=book_author, back_populates='books')

    # self-referential relationship - a book can recommend many other books
    recommendations = relationship('Book',
                                   secondary=recommendation_table,
                                   primaryjoin=faust == recommendation_table.c.book_faust,
                                   secondaryjoin=faust == recommendation_table.c.recommended_faust,
                                   backref='recommended_by')


class Author(Base):
    __tablename__ = 'author'

    name = Column(String, primary_key=True)
    books = relationship('Book', secondary=book_author, back_populates='authors')


engine = create_engine('sqlite:///scraped_books_only_top10k_test.db')
Base.metadata.create_all(engine)


def create_session():
    Session = sessionmaker(bind=engine)
    session = Session()
    return session
