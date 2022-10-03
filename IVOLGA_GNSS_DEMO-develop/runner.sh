mkdir -p logs
cd testFrontend
nohup python3 FlaskConsumer.py &
cd ..
python3 main.py