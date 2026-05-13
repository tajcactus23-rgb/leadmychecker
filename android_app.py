"""
Lotterywest Checker Android App
Webview that loads your checker results
"""

import kivy
kivy.require('2.1.0')

from kivy.app import App
from kivy.uix.progressbar import ProgressBar
from kivy.uix.webview import WebView
from kivy.uix.boxlayout import BoxLayout
from kivy.network import UrlRequest

# Change this to your server URL when deployed
SERVER_URL = "https://work-1-irzgcaoibopkpfen.prod-runtime.all-hands.dev"

class LotterywestApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical')
        
        # Loading indicator
        self.progress = ProgressBar(max=100, value=0)
        layout.add_widget(self.progress)
        
        # WebView
        self.webview = WebView(url=SERVER_URL, 
                          progress=self.progress)
        layout.add_widget(self.webview)
        
        return layout

if __name__ == '__main__':
    LotterywestApp().run()