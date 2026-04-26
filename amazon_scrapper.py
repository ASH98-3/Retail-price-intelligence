import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, random, pandas as pd, datetime, os

# ── Categories to scrape and their Amazon India search URLs ──────────────────
CATEGORIES = {
    "smartphones":     "https://www.amazon.in/s?k=smartphones",
    "laptops":         "https://www.amazon.in/s?k=laptops",
    "home_appliances": "https://www.amazon.in/s?k=home+appliances"
}

MAX_PAGES = 15   # 15 pages × ~40 products = ~600 products per category

# ── Browser setup ────────────────────────────────────────────────────────────
def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1366,768")
    # Disables the flag that tells websites this is an automated browser
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Do NOT add --headless — Amazon detects and blocks headless browsers
    driver = uc.Chrome(options=options, version_main=147)
    driver.maximize_window()
    return driver

# ── Random delay to mimic human browsing speed ───────────────────────────────
def random_delay(min_s=3, max_s=7):
    time.sleep(random.uniform(min_s, max_s))

# ── Extract all fields from a single product card ────────────────────────────
def extract_product(card, category):

    # ── Name ─────────────────────────────────────────────────────────────────
    # h2.a-size-medium contains the full product title inside a span
    try:
        name = card.find_element(
            By.CSS_SELECTOR, "h2.a-size-medium span"
        ).text.strip()
        if not name:
            return None
    except:
        return None

    # ── Current selling price ─────────────────────────────────────────────────
    # span.a-price-whole contains the number e.g. "12,499"
    # some cards hide price in a-offscreen — try both
    try:
        price_raw = card.find_element(
            By.CSS_SELECTOR, "span.a-price-whole"
        ).text
        price = float(price_raw.replace(",", "").strip())
    except:
        try:
            # fallback — some cards hide price inside a-offscreen span
            # must use textContent because .text returns empty for hidden elements
            price_raw = card.find_element(
                By.CSS_SELECTOR, "span.a-price span.a-offscreen"
            ).get_attribute("textContent")
            price = float(price_raw.replace("₹", "").replace(",", "").strip())
        except:
            price = None

    # ── MRP (crossed out original price) ─────────────────────────────────────
    # a-offscreen is CSS hidden so .text returns empty string
    # get_attribute("textContent") reads hidden content directly
    try:
        mrp_element = card.find_element(
            By.CSS_SELECTOR, "span.a-price.a-text-price span.a-offscreen"
        )
        mrp_raw = mrp_element.get_attribute("textContent")
        mrp = float(
            mrp_raw.replace("₹", "").replace(",", "").strip()
        )
        if not mrp:
            mrp = price
    except:
        # no strikethrough price shown = seller not claiming a discount
        mrp = price

    # ── Discount % ───────────────────────────────────────────────────────────
    # shown as "(11% off)" in a plain span — not present on all products
    # fallback: calculate from price and MRP if not shown explicitly
    discount_pct = None
    try:
        discount_raw = card.find_element(
            By.XPATH, ".//span[contains(text(), '% off')]"
        ).text
        # "(11% off)" → 11.0
        discount_pct = float(
            discount_raw.replace("(", "").replace("% off)", "").strip()
        )
    except:
        if price and mrp and mrp > price:
            discount_pct = round((mrp - price) / mrp * 100, 1)

    # ── Star rating ───────────────────────────────────────────────────────────
    # aria-hidden span shows "4.0" as plain visible text — cleaner than icon
    # fallback reads from the icon alt text via XPATH
    try:
        rating_raw = card.find_element(
            By.CSS_SELECTOR, "span[aria-hidden='true'].a-size-small.a-color-base"
        ).text.strip()
        rating = float(rating_raw)
    except:
        try:
            # fallback — read rating from icon alt text
            rating_raw = card.find_element(
                By.XPATH, ".//span[contains(@class,'a-icon-alt')]"
            ).get_attribute("innerHTML")
            rating = float(rating_raw.split()[0])
        except:
            rating = None

    # ── Review count ──────────────────────────────────────────────────────────
    # aria-label on ratings anchor has exact count e.g. "2,639 ratings"
    # better than visible "(2.6K)" text which is truncated
    try:
        reviews_raw = card.find_element(
            By.CSS_SELECTOR, "a[aria-label*='ratings']"
        ).get_attribute("aria-label")
        # "2,639 ratings" → 2639
        reviews = int(reviews_raw.replace(",", "").split()[0])
    except:
        reviews = None

    # ── Brand ─────────────────────────────────────────────────────────────────
    # no separate brand element on listing page
    # extract first word from product name as brand proxy
    brand = name.split()[0] if name else None

    # ── In stock ──────────────────────────────────────────────────────────────
    # products without a price on listing page are typically unavailable
    in_stock = 1 if price else 0

    # ── Delivery info ─────────────────────────────────────────────────────────
    # udm-primary-delivery-message holds "FREE delivery Mon, 27 Apr"
    try:
        delivery = card.find_element(
            By.CSS_SELECTOR, "div.udm-primary-delivery-message div"
        ).text.strip()
    except:
        delivery = None

    return {
        "name":          name,
        "brand":         brand,
        "category":      category,
        "price":         price,
        "mrp":           mrp,
        "discount_pct":  discount_pct,
        "rating":        rating,
        "reviews":       reviews,
        "in_stock":      in_stock,
        "delivery_info": delivery,
        "seller_count":  None,   # only available on product detail page
        "source":        "amazon",
        "scrape_day":    datetime.date.today().isoformat(),
        "timestamp":     datetime.datetime.now().isoformat()
    }

# ── Scrape all pages for one category ────────────────────────────────────────
def scrape_category(driver, category, url):
    all_products = []
    seen_names = set()   # prevents duplicate products across pages

    for page in range(1, MAX_PAGES + 1):
        paged_url = f"{url}&page={page}"
        print(f"  [{category}] Page {page}/{MAX_PAGES}")

        try:
            driver.get(paged_url)
            random_delay(3, 6)

            # Wait until product cards are present before extracting
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-component-type="s-search-result"]')
                )
            )
        except:
            print(f"  Page {page} failed to load — skipping")
            continue

        cards = driver.find_elements(
            By.CSS_SELECTOR, '[data-component-type="s-search-result"]'
        )

        page_count = 0
        for card in cards:
            product = extract_product(card, category)
            # Only save if extraction succeeded and name is not a duplicate
            if product and product["name"] not in seen_names:
                seen_names.add(product["name"])
                all_products.append(product)
                page_count += 1

        print(f"  → {page_count} new | total: {len(all_products)}")

        # Every 5 pages take a longer human-like break
        if page % 5 == 0:
            pause = random.uniform(15, 25)
            print(f"  Long break: {pause:.0f}s...")
            time.sleep(pause)

    return all_products

#Main entry point 
def run():
    today = datetime.date.today()
    print("=" * 50)
    print(f"Amazon scraper — {today}")
    print("=" * 50)

    # Each day gets its own dated subfolder — files never overwrite each other
    folder = f"data/amazon/day_{today}"
    os.makedirs(folder, exist_ok=True)

    driver = get_driver()
    all_data = []

    for category, url in CATEGORIES.items():
        print(f"\nScraping: {category.upper()}")
        products = scrape_category(driver, category, url)
        all_data.extend(products)
        print(f"  Finished {category} — {len(products)} products")
        # Pause between categories to avoid triggering rate limits
        time.sleep(random.uniform(10, 20))

    driver.quit()

    # Save all categories into one CSV inside the dated folder
    df = pd.DataFrame(all_data)
    filepath = f"{folder}/amazon_{today}.csv"
    df.to_csv(filepath, index=False)

    print(f"\nSaved {len(df)} products → {filepath}")
    print(f"Category breakdown:\n{df['category'].value_counts()}")

if __name__ == "__main__":
    run()