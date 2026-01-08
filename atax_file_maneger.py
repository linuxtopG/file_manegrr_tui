#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import curses
import stat
import time
import subprocess
from pathlib import Path
from datetime import datetime
import pwd
import grp

class FileManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_path = Path.home()
        self.selected_index = 0
        self.top_index = 0
        self.files = []
        self.sort_by = 'name'
        self.sort_reverse = False
        self.pane_height = 0
        self.show_hidden = False
        self.clipboard = None
        self.clipboard_type = None  # 'copy' or 'cut'
        self.search_mode = False
        self.search_query = ""
        self.quit = False
        
    def refresh_files(self):
        """تحديث قائمة الملفات في المسار الحالي"""
        try:
            all_files = list(self.current_path.iterdir())
            
            # تصفية الملفات المخفية
            if not self.show_hidden:
                all_files = [f for f in all_files if not f.name.startswith('.')]
            
            # فصل المجلدات والملفات
            dirs = [f for f in all_files if f.is_dir()]
            files = [f for f in all_files if not f.is_dir()]
            
            # ترتيب المجلدات أولاً
            if self.sort_by == 'name':
                dirs.sort(key=lambda x: x.name.lower(), reverse=self.sort_reverse)
                files.sort(key=lambda x: x.name.lower(), reverse=self.sort_reverse)
            elif self.sort_by == 'size':
                dirs.sort(key=lambda x: x.stat().st_size if x.exists() else 0, reverse=self.sort_reverse)
                files.sort(key=lambda x: x.stat().st_size if x.exists() else 0, reverse=self.sort_reverse)
            elif self.sort_by == 'modified':
                dirs.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=self.sort_reverse)
                files.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=self.sort_reverse)
            elif self.sort_by == 'type':
                dirs.sort(key=lambda x: x.suffix.lower(), reverse=self.sort_reverse)
                files.sort(key=lambda x: x.suffix.lower(), reverse=self.sort_reverse)
            
            self.files = dirs + files
            
            # تطبيق البحث إذا كان مفعلاً
            if self.search_mode and self.search_query:
                self.files = [f for f in self.files 
                            if self.search_query.lower() in f.name.lower()]
            
        except PermissionError:
            self.files = []
            
    def format_size(self, size):
        """تنسيق حجم الملف"""
        for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PiB"
    
    def get_file_info(self, filepath):
        """الحصول على معلومات الملف"""
        try:
            stat_info = filepath.stat()
            
            # الحصول على صلاحيات الملف
            mode = stat_info.st_mode
            permissions = ''
            for who in "USR", "GRP", "OTH":
                for perm in "R", "W", "X":
                    if mode & getattr(stat, f"S_I{perm}{who}"):
                        permissions += perm.lower()
                    else:
                        permissions += '-'
            
            # الحصول على المالك والمجموعة
            try:
                owner = pwd.getpwuid(stat_info.st_uid).pw_name
            except:
                owner = str(stat_info.st_uid)
            
            try:
                group = grp.getgrgid(stat_info.st_gid).gr_name
            except:
                group = str(stat_info.st_gid)
            
            # تنسيق الوقت
            mod_time = datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')
            
            return {
                'size': self.format_size(stat_info.st_size),
                'permissions': permissions,
                'owner': owner,
                'group': group,
                'modified': mod_time,
                'inode': stat_info.st_ino
            }
        except:
            return {
                'size': '0 B',
                'permissions': '????????',
                'owner': '?',
                'group': '?',
                'modified': '????-??-?? ??:??',
                'inode': '?'
            }
    
    def draw_ui(self):
        """رسم واجهة المستخدم"""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        self.pane_height = height - 5
        
        # شريط العنوان
        title = f"  File Manager - {self.current_path}  "
        if self.search_mode:
            title = f"  Search: {self.search_query}  "
        title_bar = title.center(width, '=')
        self.stdscr.addstr(0, 0, title_bar[:width-1], curses.A_REVERSE)
        
        # معلومات المسار
        path_info = f"Path: {self.current_path}"
        self.stdscr.addstr(1, 0, path_info[:width-1])
        
        # رأس القائمة
        header = "Permissions    Owner    Group    Size        Modified             Name"
        self.stdscr.addstr(2, 0, header[:width-1], curses.A_BOLD)
        
        # عرض الملفات
        start = self.top_index
        end = min(start + self.pane_height, len(self.files))
        
        for i in range(start, end):
            idx = i - start
            file = self.files[i]
            
            # تحضير المعلومات
            info = self.get_file_info(file)
            
            # تحديد اللون حسب نوع الملف
            color = curses.A_NORMAL
            if file.is_dir():
                color = curses.A_BOLD | curses.color_pair(1)  # أزرق للمجلدات
            elif file.is_symlink():
                color = curses.color_pair(2)  # سماوي للروابط
            elif os.access(file, os.X_OK):
                color = curses.color_pair(3)  # أخضر للملفات القابلة للتنفيذ
            
            # إذا كان الملف محدد
            if i == self.selected_index:
                color |= curses.A_REVERSE
            
            # بناء سطر المعلومات
            line = f"{info['permissions']:11} {info['owner']:8} {info['group']:8} "
            line += f"{info['size']:11} {info['modified']:19} {file.name}"
            
            # اقتصار السطر لعرضه في النافذة
            self.stdscr.addstr(3 + idx, 0, line[:width-1], color)
        
        # شريط الحالة
        status_line = 3 + self.pane_height
        if status_line < height - 1:
            # معلومات الملف المحدد
            if self.files and 0 <= self.selected_index < len(self.files):
                selected_file = self.files[self.selected_index]
                info = self.get_file_info(selected_file)
                file_type = "Directory" if selected_file.is_dir() else "File"
                status = f"{file_type}: {selected_file.name} | Size: {info['size']} | Permissions: {info['permissions']}"
            else:
                status = "No files"
            
            # إضافة معلومات التصفية والترتيب
            status += f" | Hidden: {'ON' if self.show_hidden else 'OFF'} | Sort: {self.sort_by}"
            if self.sort_reverse:
                status += " (reverse)"
            
            self.stdscr.addstr(status_line, 0, status[:width-1])
            
            # شريط الأوامر
            cmd_line = status_line + 1
            if cmd_line < height:
                commands = "F1:Help | F2:Rename | F3:View | F4:Edit | F5:Copy | F6:Move | F7:New Dir | F8:Delete | F9:Sort | F10:Quit"
                self.stdscr.addstr(cmd_line, 0, commands[:width-1], curses.A_REVERSE)
    
    def navigate_to_parent(self):
        """الانتقال إلى المجلد الأعلى"""
        if self.current_path != Path('/'):
            self.current_path = self.current_path.parent
            self.selected_index = 0
            self.top_index = 0
            self.refresh_files()
    
    def navigate_into(self):
        """الدخول إلى المجلد المحدد"""
        if self.files and 0 <= self.selected_index < len(self.files):
            selected = self.files[self.selected_index]
            if selected.is_dir():
                try:
                    self.current_path = selected
                    self.selected_index = 0
                    self.top_index = 0
                    self.refresh_files()
                except PermissionError:
                    self.show_message("Permission denied!")
    
    def show_message(self, message, delay=2):
        """عرض رسالة مؤقتة"""
        height, width = self.stdscr.getmaxyx()
        msg_line = height - 2 if height > 2 else 0
        self.stdscr.addstr(msg_line, 0, message[:width-1], curses.A_REVERSE)
        self.stdscr.refresh()
        curses.napms(delay * 1000)
    
    def get_input(self, prompt):
        """الحصول على إدخال من المستخدم"""
        height, width = self.stdscr.getmaxyx()
        input_line = height - 2 if height > 2 else 0
        
        # مسح السطر
        self.stdscr.addstr(input_line, 0, " " * (width-1))
        
        # عرض المطالبة
        self.stdscr.addstr(input_line, 0, prompt)
        self.stdscr.refresh()
        
        # تفعيل echo مؤقتاً
        curses.echo()
        curses.curs_set(1)
        
        # قراءة الإدخال
        try:
            input_str = self.stdscr.getstr(input_line, len(prompt)).decode('utf-8')
        except:
            input_str = ""
        
        # إعادة تعيين الإعدادات
        curses.noecho()
        curses.curs_set(0)
        
        return input_str
    
    def create_new_directory(self):
        """إنشاء مجلد جديد"""
        name = self.get_input("New directory name: ")
        if name:
            try:
                new_dir = self.current_path / name
                new_dir.mkdir(exist_ok=False)
                self.refresh_files()
                self.show_message(f"Directory '{name}' created successfully!")
            except FileExistsError:
                self.show_message(f"Directory '{name}' already exists!")
            except Exception as e:
                self.show_message(f"Error: {str(e)}")
    
    def delete_file(self):
        """حذف ملف أو مجلد"""
        if self.files and 0 <= self.selected_index < len(self.files):
            target = self.files[self.selected_index]
            
            # تأكيد الحذف
            confirm = self.get_input(f"Delete '{target.name}'? (y/N): ")
            if confirm.lower() == 'y':
                try:
                    if target.is_dir():
                        import shutil
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    
                    self.refresh_files()
                    self.show_message(f"'{target.name}' deleted successfully!")
                except Exception as e:
                    self.show_message(f"Error deleting: {str(e)}")
    
    def rename_file(self):
        """إعادة تسمية ملف أو مجلد"""
        if self.files and 0 <= self.selected_index < len(self.files):
            old_file = self.files[self.selected_index]
            new_name = self.get_input(f"Rename '{old_file.name}' to: ")
            
            if new_name:
                try:
                    new_path = self.current_path / new_name
                    old_file.rename(new_path)
                    self.refresh_files()
                    self.show_message(f"Renamed to '{new_name}' successfully!")
                except Exception as e:
                    self.show_message(f"Error renaming: {str(e)}")
    
    def copy_file(self):
        """نسخ ملف إلى الحافظة"""
        if self.files and 0 <= self.selected_index < len(self.files):
            self.clipboard = self.files[self.selected_index]
            self.clipboard_type = 'copy'
            self.show_message(f"'{self.clipboard.name}' copied to clipboard")
    
    def cut_file(self):
        """قص ملف إلى الحافظة"""
        if self.files and 0 <= self.selected_index < len(self.files):
            self.clipboard = self.files[self.selected_index]
            self.clipboard_type = 'cut'
            self.show_message(f"'{self.clipboard.name}' cut to clipboard")
    
    def paste_file(self):
        """لصق ملف من الحافظة"""
        if self.clipboard:
            try:
                dest = self.current_path / self.clipboard.name
                
                if self.clipboard_type == 'copy':
                    import shutil
                    if self.clipboard.is_dir():
                        shutil.copytree(self.clipboard, dest)
                    else:
                        shutil.copy2(self.clipboard, dest)
                    self.show_message(f"'{self.clipboard.name}' copied successfully!")
                
                elif self.clipboard_type == 'cut':
                    import shutil
                    shutil.move(self.clipboard, dest)
                    self.show_message(f"'{self.clipboard.name}' moved successfully!")
                    self.clipboard = None
                    self.clipboard_type = None
                
                self.refresh_files()
                
            except Exception as e:
                self.show_message(f"Error pasting: {str(e)}")
    
    def change_sort(self):
        """تغيير طريقة الترتيب"""
        sort_options = ['name', 'size', 'modified', 'type']
        current_idx = sort_options.index(self.sort_by) if self.sort_by in sort_options else 0
        next_idx = (current_idx + 1) % len(sort_options)
        self.sort_by = sort_options[next_idx]
        self.refresh_files()
        self.show_message(f"Sorted by: {self.sort_by}")
    
    def toggle_hidden(self):
        """تبديل عرض الملفات المخفية"""
        self.show_hidden = not self.show_hidden
        self.refresh_files()
        self.show_message(f"Hidden files: {'ON' if self.show_hidden else 'OFF'}")
    
    def toggle_sort_reverse(self):
        """تبديل اتجاه الترتيب"""
        self.sort_reverse = not self.sort_reverse
        self.refresh_files()
        self.show_message(f"Sort reversed: {'ON' if self.sort_reverse else 'OFF'}")
    
    def view_file(self):
        """عرض محتوى الملف"""
        if self.files and 0 <= self.selected_index < len(self.files):
            file = self.files[self.selected_index]
            if file.is_file():
                try:
                    # حفظ إعدادات curses مؤقتاً
                    curses.endwin()
                    
                    # استخدام less لعرض الملف
                    subprocess.run(['less', str(file)])
                    
                    # إعادة تهيئة curses
                    self.stdscr.clear()
                    self.stdscr.refresh()
                except Exception as e:
                    curses.endwin()
                    print(f"Error viewing file: {e}")
                    input("Press Enter to continue...")
                    self.stdscr.clear()
                    self.stdscr.refresh()
    
    def edit_file(self):
        """تحرير ملف باستخدام محرر نصي"""
        if self.files and 0 <= self.selected_index < len(self.files):
            file = self.files[self.selected_index]
            if file.is_file():
                try:
                    # حفظ إعدادات curses مؤقتاً
                    curses.endwin()
                    
                    # محاولة استخدام vim، ثم nano، ثم vi
                    editors = ['vim', 'nano', 'vi']
                    for editor in editors:
                        if subprocess.run(['which', editor], capture_output=True).returncode == 0:
                            subprocess.run([editor, str(file)])
                            break
                    
                    # إعادة تهيئة curses
                    self.stdscr.clear()
                    self.stdscr.refresh()
                except Exception as e:
                    curses.endwin()
                    print(f"Error editing file: {e}")
                    input("Press Enter to continue...")
                    self.stdscr.clear()
                    self.stdscr.refresh()
    
    def show_help(self):
        """عرض شاشة المساعدة"""
        help_text = [
            "=== File Manager Help ===",
            "",
            "Navigation:",
            "  ↑/↓     : Move selection",
            "  PageUp  : Scroll up",
            "  PageDown: Scroll down",
            "  Home    : Go to first item",
            "  End     : Go to last item",
            "  Enter   : Open directory/file",
            "  Backspace: Go to parent directory",
            "",
            "File Operations:",
            "  F2      : Rename",
            "  F3      : View file content",
            "  F4      : Edit file",
            "  F5      : Copy",
            "  F6      : Cut/Move",
            "  F7      : New directory",
            "  F8      : Delete",
            "  F9      : Change sort method",
            "  F10     : Quit",
            "",
            "Other Commands:",
            "  Ctrl+H  : Toggle hidden files",
            "  Ctrl+R  : Reverse sort order",
            "  /       : Search files",
            "  Esc     : Cancel search",
            "  v       : Paste from clipboard",
            "",
            "Press any key to return..."
        ]
        
        # حفظ إعدادات curses مؤقتاً
        curses.endwin()
        
        # عرض المساعدة
        print("\n".join(help_text))
        input("\nPress Enter to continue...")
        
        # إعادة تهيئة curses
        self.stdscr.clear()
        self.stdscr.refresh()
    
    def run(self):
        """الدالة الرئيسية لتشغيل مدير الملفات"""
        # تهيئة الألوان
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)    # أزرق للمجلدات
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)    # سماوي للروابط
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)   # أخضر للتنفيذ
        
        curses.curs_set(0)  # إخفاء المؤشر
        curses.noecho()     # عدم عرض الأحرف المكتوبة
        
        self.refresh_files()
        
        while not self.quit:
            self.draw_ui()
            key = self.stdscr.getch()
            
            # التعامل مع ضغطات المفاتيح
            if self.search_mode:
                if key == 27:  # ESC
                    self.search_mode = False
                    self.search_query = ""
                    self.refresh_files()
                elif key == 10 or key == 13:  # Enter
                    self.search_mode = False
                    self.refresh_files()
                elif key == curses.KEY_BACKSPACE or key == 127:
                    self.search_query = self.search_query[:-1]
                    self.refresh_files()
                elif 32 <= key <= 126:  # أحرف عادية
                    self.search_query += chr(key)
                    self.refresh_files()
                continue
            
            if key == curses.KEY_UP:
                if self.selected_index > 0:
                    self.selected_index -= 1
                    if self.selected_index < self.top_index:
                        self.top_index = self.selected_index
            
            elif key == curses.KEY_DOWN:
                if self.selected_index < len(self.files) - 1:
                    self.selected_index += 1
                    if self.selected_index >= self.top_index + self.pane_height:
                        self.top_index = self.selected_index - self.pane_height + 1
            
            elif key == curses.KEY_PPAGE:  # Page Up
                if self.selected_index > 0:
                    self.selected_index = max(0, self.selected_index - self.pane_height)
                    if self.selected_index < self.top_index:
                        self.top_index = self.selected_index
            
            elif key == curses.KEY_NPAGE:  # Page Down
                if self.files:
                    self.selected_index = min(len(self.files) - 1, 
                                            self.selected_index + self.pane_height)
                    if self.selected_index >= self.top_index + self.pane_height:
                        self.top_index = self.selected_index - self.pane_height + 1
            
            elif key == curses.KEY_HOME:
                self.selected_index = 0
                self.top_index = 0
            
            elif key == curses.KEY_END:
                if self.files:
                    self.selected_index = len(self.files) - 1
                    self.top_index = max(0, len(self.files) - self.pane_height)
            
            elif key == 10 or key == 13:  # Enter
                self.navigate_into()
            
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.navigate_to_parent()
            
            elif key == ord('/'):
                self.search_mode = True
                self.search_query = ""
            
            elif key == ord('v'):
                self.paste_file()
            
            # مفاتيح الوظائف
            elif key == curses.KEY_F1:
                self.show_help()
            
            elif key == curses.KEY_F2:
                self.rename_file()
            
            elif key == curses.KEY_F3:
                self.view_file()
            
            elif key == curses.KEY_F4:
                self.edit_file()
            
            elif key == curses.KEY_F5:
                self.copy_file()
            
            elif key == curses.KEY_F6:
                self.cut_file()
            
            elif key == curses.KEY_F7:
                self.create_new_directory()
            
            elif key == curses.KEY_F8:
                self.delete_file()
            
            elif key == curses.KEY_F9:
                self.change_sort()
            
            elif key == curses.KEY_F10:
                self.quit = True
            
            # اختصارات أخرى
            elif key == ord('h') and curses.KEY_CTRL:  # Ctrl+H
                self.toggle_hidden()
            
            elif key == ord('r') and curses.KEY_CTRL:  # Ctrl+R
                self.toggle_sort_reverse()
            
            elif key == ord('q'):  # Q للخروج
                self.quit = True
            
            # تحديث العرض بعد كل إجراء
            self.refresh_files()

def main():
    try:
        curses.wrapper(lambda stdscr: FileManager(stdscr).run())
    except KeyboardInterrupt:
        pass
    finally:
        print("File Manager terminated.")

if __name__ == "__main__":
    main()
