#! /bin/bash
# Make a debian/ubuntu distribution
# Workaround for broken inkscape extension localization:
# - We have multiple *.inx files, one per language.
# - we have multiple make install* targets, one per language.
# - we build multiple binary *.deb packages, one per language.

name=$1
vers=$2
url=http://github.com/jnweiger/$name

build_deb_package() {
  pkgname=$1
  maketarget=$2
  fakeroot checkinstall --fstrans --reset-uid --type debian \
    --install=no -y --pkgname $pkgname --pkgversion $vers --arch all \
    --pkgrelease=$(date +%Y%m%d)jw --pkglicense LGPL --pkggroup other \
    --pakdir ../$tmp --pkgsource $url \
    --maintainer "'Juergen Weigert (juergen@fabmail.org)'" \
    make $maketarget -e PREFIX=/usr || { echo "fakeroot checkinstall error "; exit 1; }
}

tmp=../out

[ -d $tmp ] && rm -rf $tmp/*.deb
mkdir -p $tmp
cp *-pak files/
cd files
build_deb_package $name    install
# build_deb_package $name-de install_de

for deb in ../$tmp/*.deb; do
  dpkg-deb --info     $deb
  dpkg-deb --contents $deb
done
