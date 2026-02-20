// LinkedIn Scraper - Gets token from LeadGen backend FIRST
const { PuppeteerCrawler, log } = require('crawlee');
const fs = require('fs');
const axios = require('axios');

// Read config
const args = process.argv.slice(2);
const configPath = args[args.indexOf('--config') + 1];
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const LINKEDIN_EMAIL = process.env.LINKEDIN_EMAIL || config.linkedin_email;
const LINKEDIN_PASSWORD = process.env.LINKEDIN_PASSWORD || config.linkedin_password;

const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

let BACKEND_TOKEN = null;

// Main execution
async function main() {
    // STEP 1: Login to LeadGen backend and get token
    log.info('━'.repeat(60));
    log.info('STEP 1: Login to LeadGen Backend');
    log.info('━'.repeat(60));
    log.info(`Backend URL: ${config.backend_url}`);
    log.info(`Login Email: ${config.backend_email}`);
    
    try {
        const loginResponse = await axios.post(
            `${config.backend_url}/api/v1/auth/login`,
            {
                email: config.backend_email,
                password: config.backend_password
            }
        );
        
        BACKEND_TOKEN = loginResponse.data.access_token;
        log.info('✅ Login successful!');
        log.info(`Token: ${BACKEND_TOKEN.substring(0, 30)}...`);
        log.info('');
        
    } catch (error) {
        log.error('❌ Failed to login to backend!');
        log.error(`Error: ${error.message}`);
        if (error.response) {
            log.error(`Response: ${JSON.stringify(error.response.data)}`);
        }
        process.exit(1);
    }
    
    // STEP 2: Start LinkedIn scraper
    log.info('━'.repeat(60));
    log.info('STEP 2: Start LinkedIn Scraper');
    log.info('━'.repeat(60));
    
    const crawler = new PuppeteerCrawler({
        launchContext: {
            launchOptions: {
                headless: false,
                args: ['--no-sandbox', '--disable-setuid-sandbox']
            }
        },
        maxConcurrency: 1,
        requestHandlerTimeoutSecs: 300,
        
        async requestHandler({ request, page }) {
            log.info(`🔍 URL: ${request.url}`);
            await wait(3000);
            
            // Login to LinkedIn
            const isLoginPage = await page.$('input#username') || await page.$('input[name="session_key"]');
            if (isLoginPage) {
                log.info('🔐 Logging in to LinkedIn...');
                await page.type('input#username, input[name="session_key"]', LINKEDIN_EMAIL);
                await page.type('input#password, input[name="session_password"]', LINKEDIN_PASSWORD);
                await page.click('button[type="submit"]');
                await page.waitForNavigation({ timeout: 30000 });
            }
            
            log.info('⏳ Waiting for results...');
            await wait(15000);
            
            // Extract profiles
            const profiles = await page.evaluate((maxResults) => {
                const results = [];
                const cards = Array.from(document.querySelectorAll('[role="listitem"]'));
                
                for (const card of cards) {
                    if (results.length >= maxResults) break;
                    
                    const nameLink = card.querySelector('a[data-view-name="search-result-lockup-title"]');
                    if (!nameLink) continue;
                    
                    const url = nameLink.href;
                    const fullName = nameLink.textContent?.trim();
                    
                    if (!url || !url.match(/^https:\/\/www\.linkedin\.com\/in\/[^/]+\/?$/)) continue;
                    if (!fullName || fullName.length < 2) continue;
                    if (results.some(p => p.linkedin_url === url)) continue;
                    
                    const allText = Array.from(card.querySelectorAll('p'))
                        .map(p => p.textContent?.trim())
                        .filter(t => t && t.length > 3);
                    
                    let headline = '';
                    for (const text of allText) {
                        if (text.includes('VP') || text.includes('Vice President') || 
                            text.includes('Engineering') || text.includes('CTO') ||
                            text.includes('Chief') || text.includes('Director')) {
                            headline = text;
                            break;
                        }
                    }
                    
                    let location = '';
                    for (const text of allText) {
                        if (text.includes(',')) {
                            location = text;
                            break;
                        }
                    }
                    
                    const nameParts = fullName.split(' ');
                    
                    results.push({
                        full_name: fullName,
                        first_name: nameParts[0] || '',
                        last_name: nameParts.slice(1).join(' ') || '',
                        headline: headline,
                        job_title: headline,
                        linkedin_url: url,
                        location: location
                    });
                }
                
                return results;
            }, config.max_results || 10);
            
            log.info(`✅ Extracted ${profiles.length} profiles`);
            profiles.slice(0, 3).forEach((p, i) => {
                log.info(`  ${i + 1}. ${p.full_name} - ${p.job_title}`);
            });
            
            // Send to backend using the token we got earlier
            if (profiles.length > 0) {
                log.info('');
                log.info('📤 Sending to backend...');
                log.info(`   Using token: ${BACKEND_TOKEN.substring(0, 30)}...`);
                
                try {
                    const response = await axios.post(
                        `${config.backend_url}/api/v1/scrapers/crawlee/batch`,
                        {
                            data_source_id: config.data_source_id,
                            scraper_type: 'crawlee',
                            source_url: request.url,
                            profiles: profiles,
                            metadata: {
                                search_keywords: config.search_keywords,
                                scraped_at: new Date().toISOString()
                            }
                        },
                        {
                            headers: { 
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${BACKEND_TOKEN}`
                            }
                        }
                    );
                    
                    log.info('✅ SUCCESS!');
                    log.info(`   Created: ${response.data.created}`);
                    log.info(`   Duplicates: ${response.data.duplicates}`);
                    log.info(`   Errors: ${response.data.errors}`);
                    
                } catch (error) {
                    log.error('❌ Backend error!');
                    log.error(`   Message: ${error.message}`);
                    if (error.response) {
                        log.error(`   Status: ${error.response.status}`);
                        log.error(`   Data: ${JSON.stringify(error.response.data)}`);
                    }
                }
            }
        },
    });
    
    const searchUrl = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(config.search_keywords)}`;
    await crawler.run([{ url: searchUrl }]);
    
    log.info('');
    log.info('━'.repeat(60));
    log.info('✅ COMPLETE!');
    log.info('━'.repeat(60));
}

main();