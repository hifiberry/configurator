git clone https://gitlab.freedesktop.org/pipewire/pipewire.git
cd pipewire
sudo apt install -y libdbus-1-dev libglib2.0-dev libsystemd-dev libreadline-dev libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libasound2-dev libjack-jackd2-dev libbluetooth-dev libsbc-dev libldacbt-enc-dev libldacbt-abr-dev libfreeaptx-dev libsndfile1-dev libsystemd-dev libudev-dev

meson setup builddir -Dgstreamer=enabled -Dsystemd=enabled -Dlogind=disabled -Dsystemd-system-service=enabled -Dsystemd-user-service=disabled -Dpipewire-alsa=enabled -Dpipewire-jack=enabled -Dalsa=enabled -Dbluez5=enabled -Dbluez5-codec-aptx=enabled -Dbluez5-codec-ldac=enabled -Dbluez5-codec-aac=disabled -Dbluez5-codec-lc3plus=disabled -Dcontrol=enabled -Daudiotestsrc=enabled -Djack=enabled -Dtest=enabled -Ddbus=enabled -Dlibcamera=disabled -Dvideoconvert=disabled -Dvideotestsrc=disabled -Dpw-cat=enabled -Dpw-cat-ffmpeg=enabled -Dudev=enabled -Dx11=disabled -Davb=disabled -Dreadline=enabled -Dcompress-offload=enabled --prefix=/usr --localstatedir=/var

meson compile -C builddir
sudo meson install -C builddir

cd
git clone https://gitlab.freedesktop.org/pipewire/wireplumber.git
cd wireplumber
meson setup builddir --prefix=/usr --localstatedir=/var -Dsystemd=enabled -Dsystemd-system-service=true -Dsystemd-us
er-service=true
meson compile -C builddir
sudo meson install -C builddir

sudo useradd --system --no-create-home --group audio pipewire
sudo usermod -aG pipewire $USER