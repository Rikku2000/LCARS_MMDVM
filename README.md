# LCARS_MMDVM

a Star Trek like LCARS for MMDVM with Display

Install:
rpi-rw
sudo apt update
sudo apt install --no-install-recommends python3-pip libsdl2-2.0-0 libsdl2-ttf-2.0-0 xserver-xorg-video-all xserver-xorg-input-all xserver-xorg-core xinit x11-xserver-utils
sudo pip3 pygame psutil
sudo chmod +x /home/pi-star/lcars_mmdvm.sh
sudo mv lcars_mmdvm.service /etc/systemd/system/lcars_mmdvm.service
sudo systemctl enable lcars_mmdvm.service
sudo systemctl daemon-reload
sudo systemctl restart lcars_mmdvm
sudo raspi-config nonint do_boot_behaviour B2
sudo reboot
