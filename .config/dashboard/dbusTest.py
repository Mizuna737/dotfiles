import dbus, dbus.mainloop.glib
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()


def onChanged(interface, changed, invalidated, sender=None):
    if interface != "org.mpris.MediaPlayer2.Player":
        return
    if "Metadata" in changed:
        meta = changed["Metadata"]
        length = meta.get("mpris:length", "NOT IN SIGNAL")
        title = meta.get("xesam:title", "NOT IN SIGNAL")
        print(f"TITLE: {title}")
        print(f"LENGTH in signal: {length}")
        if length != "NOT IN SIGNAL":
            print(f"LENGTH in seconds: {int(length) / 1e6:.1f}s")
        print("---")


bus.add_signal_receiver(
    onChanged,
    dbus_interface="org.freedesktop.DBus.Properties",
    signal_name="PropertiesChanged",
    path="/org/mpris/MediaPlayer2",
    sender_keyword="sender",
)

GLib.MainLoop().run()
