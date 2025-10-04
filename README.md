# LCARS_MMDVM

a Star Trek like LCARS for MMDVM with Display

Install:

rpi-rw</br>
sudo apt update</br>
sudo apt install --no-install-recommends python3-pip libsdl2-2.0-0 libsdl2-ttf-2.0-0 xserver-xorg-video-all xserver-xorg-input-all xserver-xorg-core xinit x11-xserver-utils</br>
sudo pip3 pygame psutil</br>
sudo chmod +x /home/pi-star/lcars_mmdvm.sh</br>
sudo mv lcars_mmdvm.service /etc/systemd/system/lcars_mmdvm.service</br>
sudo systemctl enable lcars_mmdvm.service</br>
sudo systemctl daemon-reload</br>
sudo systemctl restart lcars_mmdvm</br>
sudo raspi-config nonint do_boot_behaviour B2</br>
sudo reboot</br>
