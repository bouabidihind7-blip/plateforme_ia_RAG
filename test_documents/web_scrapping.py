import requests
from bs4 import BeautifulSoup

page = requests.get("http://books.toscrape.com/")

def main(page):
    src = page.content
    soup = BeautifulSoup(src, "lxml")
    books_details = []
    books_titles=[]
    sidebar = soup.find("aside", {"class": "sidebar col-sm-4 col-md-3"})

    def get_books_genres(sidebar):
        books_genres = sidebar.find_all("a")
        for book in books_genres:
            book_genre = book.text.strip()
            books_details.append(book_genre)
        return books_details  
    result = get_books_genres(sidebar)  # ← appel UNE SEULE FOIS, depuis main()
    print(result)

    books_titles=soup.find_all('article',{'class':'product_pod'})
    
    def get_books_titles(books_titles):
        titles_list = []                      # ← nouvelle liste séparée
        for title in books_titles:
                 book_title = title.text.strip()
                 titles_list.append(book_title)    # ← on ajoute ICI, pas dans books_titles
        return titles_list
        
     

    result1 = get_books_titles(books_titles)  # ← appel UNE SEULE FOIS, depuis main()
    print(result1)  

    books=soup.find_all('div',{'class':'col-sm-6 product_main'})
    number_of_books=len(books)


    def get_book_details(books):
         books_in_details = []
         for book in books:
            title = book.find('h1').text.strip()
            price = book.find('p', {'class': 'price_color'}).text.strip()
            books_in_details.append({"title": title, "price": price})  # dict pour garder titre+prix ensemble
         return books_in_details










main(page)  