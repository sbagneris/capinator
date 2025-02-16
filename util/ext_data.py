from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import random
from bs4 import BeautifulSoup

# URL of the page containing the scrollable table
url = "https://www.digikey.com/en/products/filter/aluminum-electrolytic-capacitors/58"  # Update with the target URL

# Initialize the webdriver (ensure chromedriver is in your PATH)
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3")

driver = webdriver.Chrome(options=chrome_options)

driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
})

driver.get(url)
time.sleep(random.uniform(20, 40))  # Wait for the page to load

# Locate the scrollable container (update the selector if needed)
scroll_container = driver.find_element(By.CSS_SELECTOR, "div[style*='overflow']")

# Scroll until the bottom of the container is reached
last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
while True:
    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
    time.sleep(random.uniform(1, 3))  # Wait for new content to load
    new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
    if new_height == last_height:
        break
    last_height = new_height

# Once fully scrolled, get the inner HTML of the container
html_content = scroll_container.get_attribute("innerHTML")
soup = BeautifulSoup(html_content, "html.parser")

# Find the table and extract its rows and columns
table = soup.find("table")
data = []
if table:
    for row in table.find_all("tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        data.append(cells)

print(data)
driver.quit()