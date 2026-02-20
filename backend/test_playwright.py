import asyncio
from playwright.async_api import async_playwright

async def test():
    print("🧪 Testing Playwright...")
    async with async_playwright() as p:
        try:
            print("  ✓ Launching Chromium...")
            browser = await p.chromium.launch(headless=True)
            
            print("  ✓ Opening new page...")
            page = await browser.new_page()
            
            print("  ✓ Navigating to example.com...")
            await page.goto('https://example.com', timeout=30000)
            
            print("  ✓ Getting page title...")
            title = await page.title()
            
            print(f"\n✅ SUCCESS! Playwright is fully working!")
            print(f"   Page title: '{title}'")
            
            await browser.close()
            return True
            
        except Exception as e:
            print(f"\n❌ FAILED! Error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    result = asyncio.run(test())
    exit(0 if result else 1)
