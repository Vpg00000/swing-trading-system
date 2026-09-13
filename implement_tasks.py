import re

# Update web/index.html
with open('web/index.html', 'r') as f:
    html = f.read()

# T-145: Change button text
html = html.replace('RUN PRICED-IN ANALYSIS', 'RUN DEEP AI ANALYSIS')

# T-146: Add LLM toggle checkboxes
llm_toggles = """
                        <div id="llm-toggles" style="display: flex; gap: 15px; margin-top: 10px; font-size: 0.85rem; color: #cbd5e1; width: 100%;">
                            <label><input type="checkbox" value="GEMINI" checked> Gemini 1.5 Pro</label>
                            <label><input type="checkbox" value="GROQ" checked> Groq Llama 3</label>
                            <label><input type="checkbox" value="DEEPSEEK" checked> DeepSeek R1</label>
                            <label><input type="checkbox" value="MISTRAL" checked> Mistral</label>
                            <label><input type="checkbox" value="OLLAMA_LOCAL"> Ollama (Local)</label>
                        </div>
"""
if 'id="llm-toggles"' not in html:
    html = html.replace('</button>\n                    </div>', '</button>\n' + llm_toggles + '                    </div>')

# T-150: Add AI Scan Progress Bar
progress_bar = """
                    <div id="aiScanProgressContainer" class="hidden" style="margin-bottom: 15px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 5px; color: #cbd5e1;">
                            <span>AI Scan Progress</span>
                            <span id="aiScanProgressText">0%</span>
                        </div>
                        <div style="width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
                            <div id="aiScanProgressBar" style="width: 0%; height: 100%; background: #10b981; transition: width 0.3s ease;"></div>
                        </div>
                        <div id="aiScanLiveStatus" style="font-size: 0.75rem; color: #94a3b8; margin-top: 5px; min-height: 16px;"></div>
                    </div>
"""
if 'id="aiScanProgressContainer"' not in html:
    html = html.replace('<div id="pricedInContainer">', progress_bar + '\n                    <div id="pricedInContainer">')

with open('web/index.html', 'w') as f:
    f.write(html)
print("Updated web/index.html")
