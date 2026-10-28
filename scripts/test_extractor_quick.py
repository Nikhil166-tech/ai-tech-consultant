import sys
import os

# Add task-1-knowledge-brain to path
sys.path.insert(0, os.path.abspath("task-1-knowledge-brain"))

from app.extractor import extract_article_content

def test_extractor():
    normal_html = '''<html>
        <head><title>Setup Webhooks | Brilliant Directories Solution Center</title></head>
        <body>
            <h1>Setup Webhooks</h1>
            <nav><a href="#">Home</a></nav>
            <p>Here is how to configure webhooks in Brilliant Directories.</p>
            <pre><code>POST /api/webhook</code></pre>
            <ul><li>Step 1</li><li>Step 2</li></ul>
            <table>
                <tr><th>Param</th><th>Type</th></tr>
                <tr><td>event</td><td>string</td></tr>
            </table>
            <img src="/images/webhook.png" alt="Webhook Diagram" />
        </body>
    </html>'''

    t, text, cat, fld, imgs, err = extract_article_content(normal_html, "https://support.brilliantdirectories.com/support/solutions/articles/123")
    assert t == "Setup Webhooks", f"Expected 'Setup Webhooks', got '{t}'"
    assert "POST /api/webhook" in text
    assert "| Param | Type |" in text
    assert len(imgs) == 1
    assert imgs[0]["url"] == "https://support.brilliantdirectories.com/images/webhook.png"
    assert err is None

    # Test login rejection
    login_html = '''<html>
        <head><title>Customer Login | Brilliant Directories</title></head>
        <body>
            <h1>Customer Login</h1>
            <p>Please enter your email and password to log in.</p>
        </body>
    </html>'''
    t, text, cat, fld, imgs, err = extract_article_content(login_html, "https://support.brilliantdirectories.com/support/login")
    assert err is not None and "login" in err.lower(), f"Expected login rejection, got {err}"

    # Test template widget rejection
    widget_html = '''<html>
        <head><title>Article Title</title></head>
        <body>
            <div class="footer-widget">
                <p>Looking for more information? Submit a ticket to our support team and we will be happy to help.</p>
            </div>
        </body>
    </html>'''
    t, text, cat, fld, imgs, err = extract_article_content(widget_html, "https://support.brilliantdirectories.com/support/solutions/articles/456")
    assert err is not None, f"Expected template rejection, got {err}"

    print("ALL EXTRACTOR TESTS PASSED!")

if __name__ == "__main__":
    test_extractor()
