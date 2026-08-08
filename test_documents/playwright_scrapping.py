import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

base_site = "https://the-internet.herokuapp.com/dynamic_loading/2"
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(
    "https://the-internet.herokuapp.com/dynamic_loading/2",
    timeout=60000,
    wait_until="domcontentloaded"
)

    # On cherche le texte "Hello World!" AVANT qu'il apparaisse (il n'existe pas encore)
    element = page.query_selector("#finish h4")
    print("Trouvé immédiatement :", element)   # → None, probablement !

    page.click("#start button")   # démarre le chargement (5 secondes d'attente sur ce site)
    page.wait_for_timeout(6000)   # on attend que ça charge

    # On réutilise la MÊME variable "element" qu'avant, sans re-chercher
    if element:
        print(element.inner_text())
    else:
        print("element est toujours None, car on ne l'a cherché QU'UNE FOIS, avant qu'il existe")

    browser.close()