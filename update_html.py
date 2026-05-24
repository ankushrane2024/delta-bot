import os

for filename in ['templates/dashboard.html', 'index.html']:
    if not os.path.exists(filename): continue
    with open(filename, 'r', encoding='utf-8') as f: content = f.read()
    
    # 1. Remove the old inline JS block
    start_str = "// --- Calculate Tomorrow's Probability ---"
    end_str = "// Update Skip & Schedule Info"
    if start_str in content and end_str in content:
        start_idx = content.find(start_str)
        end_idx = content.find(end_str)
        content = content[:start_idx] + content[end_idx:]
    
    # 2. Add the new fetchTradeProbability function after fetchNews
    new_func = """
        async function fetchTradeProbability() {
            try {
                const res = await fetch('/api/trade_probability');
                if(!res.ok) return;
                const data = await res.json();
                
                const prob = data.probability;
                let titleColor = 'var(--success)';
                if (data.verdict_level === 'medium') titleColor = 'var(--warning)';
                if (data.verdict_level === 'low' || data.verdict_level === 'none') titleColor = 'var(--danger)';
                
                document.getElementById('prob-title').textContent = data.verdict;
                document.getElementById('prob-title').style.color = titleColor;
                document.getElementById('prob-percent').textContent = prob + '%';
                
                const gaugePath = document.getElementById('prob-gauge-path');
                if (gaugePath) {
                    gaugePath.setAttribute('stroke-dasharray', prob + ', 100');
                    gaugePath.setAttribute('stroke', titleColor);
                }
                
                // Set Factors
                const fSched = data.factors.find(f => f.name === 'Schedule') || {};
                const fNews = data.factors.find(f => f.name.includes('News')) || {};
                let schedHtml = '<span class="prob-positive">Clear</span>';
                if(fSched.status === 'bad') schedHtml = `<span class="prob-negative">${fSched.label}</span>`;
                if(fNews.status === 'bad') schedHtml += ` <br><span class="prob-negative">${fNews.label}</span>`;
                else if(fNews.status === 'neutral') schedHtml += ` <br><span class="prob-neutral">${fNews.label}</span>`;
                document.getElementById('prob-schedule').innerHTML = schedHtml;
                
                const fIv = data.factors.find(f => f.name.includes('IV')) || {};
                let ivClass = fIv.status === 'good' ? 'prob-positive' : (fIv.status === 'bad' ? 'prob-negative' : 'prob-neutral');
                document.getElementById('prob-iv').innerHTML = `<span class="${ivClass}">${fIv.label}</span>`;
                
                const fAdx = data.factors.find(f => f.name.includes('ADX')) || {};
                let adxClass = fAdx.status === 'good' ? 'prob-positive' : (fAdx.status === 'bad' ? 'prob-negative' : 'prob-neutral');
                document.getElementById('prob-adx').innerHTML = `<span class="${adxClass}">${fAdx.label}</span>`;
                
            } catch(e) {
                console.error('Failed to fetch trade probability', e);
            }
        }
"""
    if 'async function fetchTradeProbability' not in content:
        # insert after fetchNews
        news_end = '} catch(e) {\n                console.error(\'News fetch failed\', e);\n            }\n        }'
        content = content.replace(news_end, news_end + '\n' + new_func)
    
    # 3. Add setInterval and initial call
    init_str = 'fetchNews();\n        setInterval(fetchNews, 6 * 60 * 60 * 1000);'
    new_init = init_str + '\n        fetchTradeProbability();\n        setInterval(fetchTradeProbability, 10 * 60 * 1000);'
    if 'fetchTradeProbability();' not in content:
        content = content.replace(init_str, new_init)
    
    with open(filename, 'w', encoding='utf-8') as f: f.write(content)
    print(f'Updated {filename}')
