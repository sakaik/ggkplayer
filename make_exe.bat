 
 rem pyinstaller --onefile --noconsole --add-data "src/icons/*.svg;icons" --console --distpath release --name ggkplayer src/main.py
 pyinstaller --onefile --noconsole --add-data "src/icons/*.svg;icons" --icon=src/icons/ggkplayer.ico --noconsole --distpath release --name ggkplayer src/main.py
