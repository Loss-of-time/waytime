# Maintainer: Aidan Heeney <aidan.heeney@proton.me>
pkgname=waytime
pkgver=0.1.0
pkgrel=1
pkgdesc="Per-app and per-website screen time tracker for KDE Plasma on Wayland"
arch=('any')
url="https://github.com/ieatfood314/waytime"
license=('MIT')
depends=('python' 'python-gobject' 'kwin')
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
    cd "$pkgname-$pkgver"
    install -Dm755 waytime "$pkgdir/usr/bin/waytime"
    install -Dm755 waytime-daemon "$pkgdir/usr/bin/waytime-daemon"
    install -Dm644 waytime_core.py "$pkgdir/usr/bin/waytime_core.py"
    install -Dm644 waytime.service "$pkgdir/usr/lib/systemd/user/waytime.service"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}
