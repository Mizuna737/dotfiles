#!/usr/bin/env python3
import argparse
import gi

# Parse args before any GTK/GDK import so WM identity is set before display init
_p = argparse.ArgumentParser()
_p.add_argument("--class", dest="wmClass", default="webkitView")
_p.add_argument("--name", dest="wmName", default=None)
_p.add_argument("--title", default="")
_p.add_argument("url")
_args = _p.parse_args()
_resClass = _args.wmClass
_resName = _args.wmName or _resClass

gi.require_version('GLib', '2.0')
gi.require_version('Gdk', '3.0')
from gi.repository import GLib, Gdk
GLib.set_prgname(_resName)
Gdk.set_program_class(_resClass)

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2


def main():
    window = Gtk.Window()
    window.set_default_size(1280, 800)
    window.set_title(_args.title)

    webView = WebKit2.WebView()
    settings = webView.get_settings()
    settings.set_property("enable-developer-extras", False)
    settings.set_property("enable-javascript", True)
    settings.set_property("enable-write-console-messages-to-stdout", False)
    webView.connect("context-menu", lambda *a: True)

    if not _args.title:
        webView.connect("notify::title", lambda wv, _: window.set_title(wv.get_title() or ""))

    window.add(webView)
    window.connect("destroy", Gtk.main_quit)

    webView.load_uri(_args.url)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
