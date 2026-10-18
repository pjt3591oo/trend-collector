"""Full-screen publisher dialogs; network work runs outside the UI thread."""
from src.publication_status import LABELS
import asyncio
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.shortcuts import message_dialog, input_dialog
from prompt_toolkit.layout.containers import HSplit, VSplit
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button as ToolkitButton, Dialog, TextArea, Label, CheckboxList, RadioList


class Button(ToolkitButton):
    """Give focused controls an unmistakable marker without changing activation."""
    def __init__(self, text, handler=None, width=16, **kwargs):
        super().__init__(text, handler=handler, width=width, **kwargs)

    def _get_text_fragments(self):
        fragments = super()._get_text_fragments()
        if not get_app().layout.has_focus(self.control):
            return fragments
        result = []
        for index, fragment in enumerate(fragments):
            style, text = fragment[:2]
            if index == 0:
                text = '▶'
            elif index == len(fragments) - 1:
                text = '◀'
            if '[SetCursorPosition]' not in style:
                style += ' class:focused-control'
            result.append((style, text, *fragment[2:]))
        return result


def emphasize_focus(widget):
    """Mark keyboard focus independently of the checked value, including wrapped rows."""
    focused = Condition(lambda: get_app().layout.has_focus(widget.control))
    widget.window.cursorline = focused

    def prefix(line_number, wrap_count):
        cursor = widget.control.create_content(width=80, height=1).cursor_position
        active = focused() and cursor is not None and line_number == cursor.y
        return [('class:focus-pointer', '▶ ' if active and wrap_count == 0 else '  ')]

    widget.window.get_line_prefix = prefix
    return widget


def radiolist_dialog(*, title='', text='', values=None, default=None,
                     ok_text='확인', cancel_text='취소', style=None):
    """Single-choice dialog with a visible focus gutter and standard selection semantics."""
    rows = emphasize_focus(RadioList(values=values or [], default=default))
    dialog = Dialog(title=title, body=HSplit([
        Label(text=text, dont_extend_height=True), rows,
        Label('▶ 현재 위치 · (*) 선택한 항목 · Tab 포커스 이동', style='class:hint'),
    ], padding=1), buttons=[
        Button(ok_text, handler=lambda: get_app().exit(result=rows.current_value)),
        Button(cancel_text, handler=lambda: get_app().exit(result=None)),
    ], with_background=True)
    bindings = KeyBindings()

    @bindings.add('escape')
    def cancel(event):
        event.app.exit(result=None)

    return Application(layout=Layout(dialog, focused_element=rows),
                       key_bindings=bindings, full_screen=True, mouse_support=True, style=style)


class ItemFilters:
    """Stable original indices, including selected rows hidden by the filters."""
    def __init__(self, items):
        self.items = items
        self.category = None
        self.source = None
        self.selected = set()

    def visible(self):
        return [i for i, item in enumerate(self.items)
                if (self.category is None or item['category'] == self.category)
                and (self.source is None or item['source'] == self.source)]

    def remember(self, visible, checked):
        self.selected.difference_update(visible)
        self.selected.update(checked)


STYLE = Style.from_dict({
    '': 'bg:#101820 #edf3f8',
    'dialog': 'bg:#182632 #edf3f8',
    'dialog.body': 'bg:#182632 #edf3f8',
    'dialog frame.label': 'bg:#182632 #6ee7c0 bold',
    'dialog frame.border': '#7b94a8',
    'dialog.body text-area': 'bg:#101820 #edf3f8',
    'text-area': 'bg:#101820 #edf3f8',
    'text-area.prompt': 'bg:#101820 #6ee7c0',
    'label': '#edf3f8',
    'hint': '#b7c9d8',
    'button': 'bg:#233746 #cad7e0',
    'button.text': 'bg:#233746 #cad7e0',
    'button.focused': 'bg:#ffd166 #101820 bold',
    'button.focused button.text': 'bg:#ffd166 #101820 bold',
    'button.arrow': '#edf3f8',
    'button.focused button.arrow': 'bg:#ffd166 #101820 bold',
    'focused-control': 'bg:#ffd166 #101820 bold',
    'radio-list': 'bg:#182632 #edf3f8',
    'radio-selected': 'bg:#253b4c #edf3f8',
    'radio-checked': '#6ee7c0',
    'checkbox-list': 'bg:#182632 #edf3f8',
    'checkbox-selected': 'bg:#253b4c #edf3f8',
    'checkbox-checked': '#6ee7c0 bold',
    'cursor-line': 'bg:#315b7b bold',
    'focus-pointer': '#ffd179 bold',
    'draft-ready': '#70d8ff bold',
    'draft-missing': '#a9b8c7 nobold',
    'publication-ready': '#6ee7a0 bold',
    'publication-warning': '#ffd179 bold',
    'publication-failed': '#ff9797 bold',
    'scrollbar.background': 'bg:#263b4b',
    'scrollbar.button': 'bg:#a7bdcc',
    'scrollbar.arrow': '#edf3f8',
    'shadow': 'bg:#080e14',
})


def item_label(item):
    ready = item.get('has_draft', False)
    status = f"초안 생성됨 {item.get('draft_count', 0)}개" if ready else '초안 미생성'
    return [('', f"{item['category']} | {item['title']}\n    "),
            ('class:draft-ready' if ready else 'class:draft-missing', status),
            ('', ' · ' if ready else ''),
            ('class:publication-ready' if item.get('published_count', 0) else 'class:draft-ready',
             f"발행 완료 {item['published_count']}개" if item.get('published_count', 0) else 'Threads 미발행' if ready else ''),
            ('', f" · {item['source']} · {item['url']}")]


class PublisherTUI:
    def choose_draft(self, item, drafts):
        labels = LABELS
        values = [('new', '＋ 새로운 초안 생성')]
        for index, draft in enumerate(drafts):
            status = draft['publication_status']
            values.append((index, [
                ('class:publication-ready' if status == 'published' else
                 'class:draft-ready' if status == 'draft' else
                 'class:publication-failed' if status == 'failed' else 'class:publication-warning',
                 f"[{labels[status]}] {draft['created_at']}\n"),
                ('', '    ' + ' '.join(draft['posts'][0]['text'].split())[:100])]))
        choice = radiolist_dialog(title='Trend Publisher · 3/5 초안 선택',
            text=f"{item['title']}\n기존 초안 {len(drafts)}개 · 기존 초안 열기 또는 새로 생성을 선택하세요.",
            values=values, default=0 if drafts else 'new',
            ok_text='선택', cancel_text='취소', style=STYLE).run()
        return choice

    def reconcile(self, draft):
        pending = [p for p in draft.get('publications', []) if p['status'] == 'pending']
        if not pending:
            return None
        index = radiolist_dialog(title='발행 결과 확인',
            text='Threads 계정에서 게시글을 직접 확인한 경우에만 진행하세요.',
            values=[(p['post_index'], f"항목 {p['post_index'] + 1}") for p in pending],
            ok_text='확인', cancel_text='취소', style=STYLE).run()
        if index is None:
            return None
        result = input_dialog(title='계정에서 확인한 결과',
            text='발행된 게시글의 숫자 ID 또는 미발행을 입력하세요. 미발행 확인 시 재발행할 수 있습니다.',
            ok_text='결과 저장', cancel_text='취소', style=STYLE).run()
        if not result:
            return None
        result = result.strip()
        return index, 'failed' if result == '미발행' else 'published', None if result == '미발행' else result

    def select_report(self, reports):
        return radiolist_dialog(title='Trend Publisher · 1/5 분석 선택',
            text='↑↓ 이동 · Space 선택 · Tab 버튼 이동 · Enter 확인',
            values=[(p['analysis_id'], f"{p['created_at']} · {p['analysis_id']}") for p in reports], ok_text='다음', cancel_text='종료', style=STYLE).run()

    def select_items(self, items, limit, refresh=None):
        filters = ItemFilters(items)
        active_tab = 'category'
        while True:
            visible = filters.visible()
            rows = emphasize_focus(CheckboxList(values=[(i, item_label(items[i]))
                for i in visible], default_values=sorted(filters.selected.intersection(visible)))) if visible else None
            summary = Label('')
            def status():
                checked = set(rows.current_values) if rows else set()
                total = len(filters.selected.difference(visible) | checked)
                hidden = len(filters.selected.difference(visible))
                return (f'카테고리: {filters.category or "전체"} · 소스: {filters.source or "전체"}\n'
                        f'표시 {len(visible)}/{len(items)}건 · 선택 {total}/{limit}개 (숨겨진 선택 {hidden}개)')
            summary.text = status
            app = None
            def finish(action):
                filters.remember(visible, rows.current_values if rows else [])
                app.exit(result=action)
            tab_buttons = VSplit([
                Button(('● ' if active_tab == 'category' else '') + '카테고리 [F1]',
                       handler=lambda: finish(('tab', 'category')), width=24),
                Button(('● ' if active_tab == 'source' else '') + '소스 [F2]',
                       handler=lambda: finish(('tab', 'source')), width=24)
            ], padding=2)
            options = [None] + sorted({item[active_tab] for item in items})
            chips = []
            for value in options:
                label = value or '전체'
                if value == getattr(filters, active_tab):
                    label = '✓ ' + label
                chips.append(Button(label, width=26, handler=lambda v=value: finish(('filter', v))))
            option_rows = HSplit([VSplit(chips[i:i+4], padding=1)
                                 for i in range(0, len(chips), 4)], padding=1)
            actions = [('필터 초기화', 'reset'),
                       ('선택 해제', 'clear'), ('초안 확인', 'generate'), ('취소', 'cancel')]
            if refresh is not None:
                actions.insert(3, ('상태 갱신', 'refresh'))
            dialog = Dialog(title='Trend Publisher · 2/5 항목 선택', body=HSplit([
                tab_buttons, option_rows, summary,
                Label('노란 ▶ 현재 포커스 · ✓ 적용 필터 · F1/F2 탭 · Tab 이동 · Space 선택', style='class:hint'),
                rows if rows else Label('일치하는 항목이 없습니다. 필터를 변경하거나 초기화하세요.')
            ], padding=1), buttons=[Button(label, handler=lambda a=action: finish(a))
                                   for label, action in actions], with_background=True,
                            width=Dimension(preferred=120))
            bindings = KeyBindings()
            @bindings.add('tab')
            def next_field(event): event.app.layout.focus_next()
            @bindings.add('s-tab')
            def previous_field(event): event.app.layout.focus_previous()
            @bindings.add('escape')
            def cancel(event): finish('cancel')
            @bindings.add('f1')
            def category_tab(event): finish(('tab', 'category'))
            @bindings.add('f2')
            def source_tab(event): finish(('tab', 'source'))
            app = Application(layout=Layout(dialog, focused_element=rows if rows else tab_buttons), key_bindings=bindings, full_screen=True,
                              mouse_support=True, style=STYLE)
            action = app.run()
            if action == 'cancel':
                return None
            if action == 'generate':
                if 1 <= len(filters.selected) <= limit:
                    return sorted(filters.selected)
                self.message('선택 확인', f'전체 선택은 1개 이상, 최대 {limit}개여야 합니다.')
            elif action == 'clear':
                filters.selected.clear()
            elif action == 'reset':
                filters.category = filters.source = None
            elif action == 'refresh':
                items = refresh()
                filters.items = items
            elif isinstance(action, tuple):
                if action[0] == 'tab':
                    active_tab = action[1]
                elif action[0] == 'filter':
                    setattr(filters, active_tab, action[1])

    def message(self, title, text):
        message_dialog(title=title, text=text, ok_text='확인', style=STYLE).run()

    def work(self, title, callback):
        result, errors = [], []
        area = TextArea(read_only=True, scrollbar=True, wrap_lines=True,
                        height=Dimension(min=4, preferred=10, max=14), style='class:text-area')
        status = Label('처리 중', style='class:hint')
        dialog = Dialog(title=title, body=HSplit([
            Label('요청을 처리하고 있습니다. 완료될 때까지 기다려 주세요.'), area, status
        ], padding=1), with_background=True, width=Dimension(preferred=96))
        app = Application(layout=Layout(dialog), full_screen=True, mouse_support=True, style=STYLE)
        async def run():
            loop = asyncio.get_running_loop()
            def log(value):
                def append():
                    area.buffer.set_document(Document(
                        area.text + value, len(area.text + value)), bypass_readonly=True)
                    app.invalidate()
                loop.call_soon_threadsafe(append)
            try:
                result.append(await asyncio.to_thread(callback, log))
            except Exception as exc:
                errors.append(exc)
            finally:
                app.exit()
        async def animate():
            count = 0
            while True:
                status.text = f"{'●' + ' ·' * (count % 4)}  처리 중 · 완료 후 다음 화면으로 이동합니다."
                app.invalidate()
                count += 1
                await asyncio.sleep(0.5)
        def start():
            app.create_background_task(run())
            app.create_background_task(animate())
        app.run(pre_run=start)
        if errors:
            raise errors[0]
        return result[0]

    def preview(self, draft):
        state_labels = LABELS
        content = '발행 상태: ' + state_labels.get(draft.get('publication_status', 'draft'), '확인 필요') + '\n\n' + ('\n\n' + '─'*45 + '\n\n').join(
            f"게시글 {i} · {len(post['text'])}자\n\n{post['text']}"
            for i, post in enumerate(draft['posts'], 1))
        for publication in draft.get('publications', []):
            if publication.get('error'):
                content += '\n\n최근 발행 오류: ' + publication['error']
        return self._read_dialog('Trend Publisher · 4/5 미리보기', content,
                                 [('게시 확인으로', True), ('취소', False)])

    def confirm(self, count):
        # Cancellation is the first/default button. Enter alone cannot publish.
        return self._read_dialog('Trend Publisher · 5/5 게시 확인',
            f'미리보기의 게시글 {count}개를 Threads 계정에 실제 업로드합니다.\n계속하려면 게시 버튼을 선택하세요.',
            [('취소', False), ('Threads에 게시', True)])

    def _read_dialog(self, title, content, choices):
        area = TextArea(text=content, read_only=True, scrollbar=True, wrap_lines=True,
                        style='class:text-area', height=Dimension(min=5, preferred=18, max=26))
        buttons = []
        app = None
        for label, value in choices:
            buttons.append(Button(label, handler=lambda v=value: app.exit(result=v)))
        dialog = Dialog(title=title, body=HSplit([
            Label('↑↓ / PageUp·PageDown 스크롤 · Tab 버튼 이동 · Esc 취소', style='class:hint'), area
        ], padding=1), buttons=buttons, with_background=True, width=Dimension(preferred=100))
        bindings = KeyBindings()
        @bindings.add('escape')
        def cancel(event): event.app.exit(result=False)
        @bindings.add('tab')
        def next_field(event): event.app.layout.focus_next()
        @bindings.add('s-tab')
        def previous_field(event): event.app.layout.focus_previous()
        app = Application(layout=Layout(dialog, focused_element=area), key_bindings=bindings,
                          full_screen=True, mouse_support=True, style=STYLE)
        return app.run()
