#!/bin/bash
# Install dependencies
sudo pacman -S fontforge p7zip jq
# Download Sarasa Gothic
wget -q $(curl 'https://api.github.com/repos/be5invis/Sarasa-Gothic/releases' | jq -r '.[0].assets | map(.browser_download_url) | map(select(test("SarasaTermSC-TTF-[0-9.]+\\.7z"))) | .[0]')
7zr x Sarasa*.7z
mkdir sarasa
mv Sarasa*.ttf sarasa

# Download Font Patcher
wget -q https://github.com/ryanoasis/nerd-fonts/raw/refs/heads/master/FontPatcher.zip
unzip FontPatcher.zip
# patch the fonts
for file in ./sarasa/*; do
   fontforge -script font-patcher $file
done
echo "now copy these new fonts to your /usr/share/fonts/TTF/"
