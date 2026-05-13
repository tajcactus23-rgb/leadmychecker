from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout

# Your server URL - change this to your deployed checker URL
SERVER_URL = "https://work-1-irzgcaoibopkpfen.prod-runtime.all-hands.dev"

class MainScreen(Screen):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=50, spacing=20)
        
        title = Label(text='[b]Lotterywest Checker[/b]', font_size=32, markup=True)
        layout.add_widget(title)
        
        info = Label(text='Open in browser to run checker', font_size=18)
        layout.add_widget(info)
        
        btn = Button(text='Open Checker', size_hint_y=None, height=60,
                   on_press=lambda x: self.open_browser())
        layout.add_widget(btn)
        
        return layout
    
    def open_browser(self):
        import webbrowser
        webbrowser.open(SERVER_URL)

class LotterywestApp(App):
    def build(self):
        sm = ScreenManager()
        screen = MainScreen(name='main')
        sm.add_widget(screen)
        return sm

if __name__ == '__main__':
    LotterywestApp().run()