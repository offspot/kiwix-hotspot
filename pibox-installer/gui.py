import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from backend import catalog
from run_installation import run_installation
import pytz
import tzlocal
import os
import sys
import threading
from util import CancelEvent
import sd_card_list
from util import human_readable_size
from datetime import datetime
import data

class Logger:
    def __init__(self, text_view, step_label):
        self.text_view = text_view
        self.text_buffer = text_view.get_buffer()
        self.step_label = step_label
        self.step_tag = self.text_buffer.create_tag("step", foreground="blue")
        self.err_tag = self.text_buffer.create_tag("err", foreground="red")

    def scroll_down(self):
        end = self.text_buffer.get_end_iter()
        end.backward_line()
        self.text_view.scroll_to_iter(end, 0, True, 0, 1.)

    def step(self, step):
        GLib.idle_add(self.main_thread_step, step)
        GLib.idle_add(self.scroll_down)

    def err(self, err):
        GLib.idle_add(self.main_thread_err, err)
        GLib.idle_add(self.scroll_down)

    def raw_std(self, std):
        GLib.idle_add(self.main_thread_raw_std, std)
        GLib.idle_add(self.scroll_down)

    def std(self, std):
        GLib.idle_add(self.main_thread_std, std)
        GLib.idle_add(self.scroll_down)

    def main_thread_step(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert_with_tags(text_iter, text + "\n", self.step_tag)
        self.step_label.set_text("Step : " + text)

    def main_thread_err(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert_with_tags(text_iter, text + "\n", self.err_tag)

    def main_thread_raw_std(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(text_iter, text)

    def main_thread_std(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(text_iter, text + "\n")

class Component:
    def __init__(self, builder):
        self.builder = builder

    def __getattr__(self, key):
        """Allow UI builder widgets to be accessed as self.widgetname"""
        widget = self.builder.get_object(key)
        if widget:
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

def validate_label(label, condition):
    color_invalid = Gdk.Color(65535, 30000, 30000)
    if condition:
        label.modify_bg(Gtk.StateFlags.NORMAL)
    else:
        label.modify_bg(Gtk.StateFlags.NORMAL, color_invalid)

class Application:
    def __init__(self, catalog):
        self.catalog = catalog

        builder = Gtk.Builder()
        builder.add_from_file(data.ui_glade)

        self.component = Component(builder)

        self.component.window.connect("delete-event", Gtk.main_quit)

        # update free space on storage change
        self.component.size_entry.connect("changed", lambda _: self.update_free_space())
        self.component.sd_card_combobox.connect("changed", lambda _: self.update_free_space())

        self.component.done_window.set_transient_for(self.component.run_window)
        self.component.done_window.set_default_size(320, 240)
        self.component.done_window.set_modal(True)
        self.component.done_window_ok_button.connect("clicked", self.done_window_ok_button_clicked)

        self.cancel_event = CancelEvent()
        self.component.run_window.connect("delete-event", Gtk.main_quit)
        self.component.run_window.set_default_size(640, 480)
        self.component.run_window.connect("delete-event", self.run_install_cancel)
        self.logger = Logger(self.component.run_text_view, self.component.run_step_label)

        self.component.run_abort_done_button.connect("clicked", self.run_abort_done_button_clicked)
        self.component.run_copy_log_to_clipboard_button.connect("clicked", self.run_copy_log_to_clipboard_button_clicked)

        # wifi password
        self.component.wifi_password_switch.connect("notify::active", lambda switch, state: self.component.wifi_password_revealer.set_reveal_child(switch.get_active()))

        # timezone
        default_id = -1
        local_tz = tzlocal.get_localzone()
        for id, timezone in enumerate(pytz.common_timezones):
            if timezone == "UTC" and default_id == -1:
                default_id = id
            if pytz.timezone(timezone) == local_tz:
                default_id = id
            self.component.timezone_tree_store.append(None, [timezone])

        renderer = Gtk.CellRendererText()
        self.component.timezone_combobox.pack_start(renderer, True)
        self.component.timezone_combobox.add_attribute(renderer, "text", 0)
        self.component.timezone_combobox.set_active(default_id)

        # disk
        types = [info["typ"] for info in sd_card_list.informations]
        self.component.sd_card_list_store = Gtk.ListStore(*types)
        self.component.sd_card_combobox.set_model(self.component.sd_card_list_store)

        for counter, _ in enumerate(filter(lambda info: info["show"], sd_card_list.informations)):
            info = Gtk.CellRendererText()
            self.component.sd_card_combobox.pack_start(info, True)
            self.component.sd_card_combobox.add_attribute(info, "text", counter)

        self.refresh_disk_list()
        self.component.sd_card_refresh_button.connect("clicked", self.sd_card_refresh_button_clicked)

        self.component.output_stack.connect("notify::visible-child", lambda switch, state: self.update_free_space())

        # zim content
        self.component.zim_choose_content_button.connect("clicked", self.zim_choose_content_button_clicked)
        self.component.run_installation_button.connect("clicked", self.run_installation_button_clicked)

        self.component.zim_list_store = Gtk.ListStore(str, str, str, str, str, str, str, str, bool, str);
        self.component.zim_list_store.set_sort_column_id(0, Gtk.SortType.ASCENDING)

        for one_catalog in catalog:
            for (key, value) in one_catalog["all"].items():
                name = value["name"]
                url = value["url"]
                description = value.get("description") or "none"
                formatted_size = human_readable_size(int(value["size"]))
                size = str(value["size"])
                language = value.get("language") or "none"
                typ = value["type"]
                version = str(value["version"])

                self.component.zim_list_store.append([key, name, url, description, formatted_size, language, typ, version, False, size])

        self.component.zim_choosen_filter = self.component.zim_list_store.filter_new()
        self.component.zim_choosen_filter.set_visible_func(self.zim_choosen_filter_func)
        self.component.zim_choosen_tree_view.set_model(self.component.zim_choosen_filter)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Id", renderer_text, text=0)
        self.component.zim_choosen_tree_view.append_column(column_text)

        self.update_free_space()

        self.component.window.show()

    def sd_card_refresh_button_clicked(self, button):
        self.refresh_disk_list()
        self.update_free_space()

    def refresh_disk_list(self):
        self.component.sd_card_list_store.clear()
        for device in sd_card_list.get_list():
            items = [info["typ"](device[info["name"]]) for info in sd_card_list.informations]
            self.component.sd_card_list_store.append(items)

    def run_install_cancel(self, widget, path):
        self.cancel_event.cancel()

    def zim_choosen_filter_func(self, model, iter, data):
        return model[iter][8]

    def zim_choose_content_button_clicked(self, button):
        ZimChooserWindow(self)

    def run_installation_button_clicked(self, button):
        all_valid = True

        project_name = self.component.project_name_entry.get_text()
        condition = project_name != ""
        validate_label(self.component.project_name_label, condition)
        all_valid = all_valid and condition

        timezone_id = self.component.timezone_combobox.get_active()
        timezone = self.component.timezone_tree_store[timezone_id][0]
        condition = timezone_id != -1
        validate_label(self.component.timezone_label, condition)
        all_valid = all_valid and condition

        if self.component.wifi_password_switch.get_state():
            wifi_pwd = self.component.wifi_password_entry.get_text()
        else:
            wifi_pwd = None

        zim_install = []
        for zim in self.component.zim_list_store:
            if zim[8]:
                zim_install.append(zim[0])

        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            condition = sd_card_id != -1
            validate_label(self.component.sd_card_label, condition)
            all_valid = all_valid and condition

            if sd_card_id == -1:
                sd_card = None
            else:
                device_index = sd_card_list.get_device_index()
                sd_card = self.component.sd_card_list_store[sd_card_id][device_index]
            output_file = False
            size = self.get_output_size()
        else:
            sd_card = None
            size = self.get_output_size()
            today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')
            filename = "pibox-{}.img".format(today)
            output_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
            if not os.path.isdir(output_dir):
                output_dir = os.path.expanduser('~')
            output_file = os.path.join(output_dir, filename)

            condition = size > 0
            validate_label(self.component.size_label, condition)
            all_valid = all_valid and condition

        condition = self.update_free_space() >= 0
        validate_label(self.component.free_space_name_label, condition)
        all_valid = all_valid and condition

        if all_valid:
            def target():
                run_installation(
                        name=project_name,
                        timezone=timezone,
                        wifi_pwd=wifi_pwd,
                        kalite=None,
                        zim_install=zim_install,
                        size=size,
                        logger=self.logger,
                        cancel_event=self.cancel_event,
                        sd_card=sd_card,
                        output_file=output_file,
                        done_callback=lambda error: GLib.idle_add(self.installation_done, error))

            self.component.window.destroy()
            self.component.run_window.show()
            threading.Thread(target=target, daemon=True).start()

    def get_free_space(self):
        # TODO: compute actual space used with empty install
        used_space = 2 * 2**30 # space of raspbian with ideascube without content
        for zim in self.component.zim_list_store:
            if zim[8]:
                used_space += int(zim[9])
        return self.get_output_size() - used_space

    def update_free_space(self):
        free_space = self.get_free_space()
        human_readable_free_space = human_readable_size(free_space)
        self.component.free_space_label1.set_text(human_readable_free_space)
        self.component.free_space_label2.set_text(human_readable_free_space)
        condition = free_space >= 0
        validate_label(self.component.free_space_label1, condition)
        validate_label(self.component.free_space_label2, condition)
        return free_space

    def get_output_size(self):
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            if sd_card_id == -1:
                size = -1
            else:
                get_size_index = sd_card_list.get_size_index()
                size = int(self.component.sd_card_list_store[sd_card_id][get_size_index])
        else:
            try:
                size = int(self.component.size_entry.get_text()) * 2**30
            except:
                size = -1

        return size

    def run_abort_done_button_clicked(self, widget):
        self.component.run_window.close()

    def run_copy_log_to_clipboard_button_clicked(self, widget):
        text_buffer = self.component.run_text_view.get_buffer()
        start = text_buffer.get_start_iter()
        end = text_buffer.get_end_iter()
        hidden = True
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text_buffer.get_text(start, end, hidden), -1)

    def done_window_ok_button_clicked(self, widget):
        self.component.done_window.close()

    def installation_done(self, error):
        if error != None:
            self.component.done_label.set_text("Installation failed: " + str(error))
            validate_label(self.component.done_label, False)
        self.component.done_window.show()
        self.component.run_abort_done_button.set_label("Close")
        self.component.run_spinner.stop()

class ZimChooserWindow:
    def __init__(self, main_window):
        builder = Gtk.Builder()
        builder.add_from_file(data.ui_glade)

        self.component = Component(builder)

        self.component.zim_list_store = main_window.component.zim_list_store
        self.main_window = main_window
        main_window.component.free_space_label2 = self.component.free_space_label2
        self.main_window.update_free_space()

        self.component.zim_tree_view.set_model(self.component.zim_list_store)

        renderer_radio = Gtk.CellRendererToggle()
        column_radio = Gtk.TreeViewColumn("Radio", renderer_radio, active=8)
        self.component.zim_tree_view.append_column(column_radio)
        renderer_radio.connect("toggled", self.renderer_radio_toggled)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Id", renderer_text, text=0)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=1)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Language", renderer_text, text=5)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Size", renderer_text, text=4)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Type", renderer_text, text=6)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Description", renderer_text, text=3)
        self.component.zim_tree_view.append_column(column_text)

        self.component.zim_window.set_transient_for(main_window.component.window)
        self.component.zim_window.set_modal(True)
        self.component.zim_window.set_default_size(1280, 800)
        self.component.zim_window.show()

        self.component.zim_window_done_button.connect("clicked", self.zim_done_button_clicked)

    def zim_done_button_clicked(self, widget):
        self.component.zim_window.close()

    def renderer_radio_toggled(self, widget, path):
        self.component.zim_list_store[path][8] = not self.component.zim_list_store[path][8]
        self.main_window.update_free_space()

catalog = catalog.get_catalogs()
Application(catalog)
Gtk.main()
