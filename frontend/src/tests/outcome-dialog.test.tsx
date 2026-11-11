import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OutcomeDialog } from '../components/OutcomeDialog';

describe('outcome dialog', () => {
  afterEach(() => vi.restoreAllMocks());
  it('reports failed modality without silently opening a nonmodal dialog', () => {
    const onFailure = vi.fn();
    const show = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
      .mockImplementation(() => { throw new Error('dialog unavailable'); });
    const view = render(<OutcomeDialog open onDismiss={vi.fn()} onStartNew={vi.fn()} onFailure={onFailure} />);
    expect(onFailure).toHaveBeenCalledOnce();
    expect(view.container.querySelector('dialog')).not.toHaveAttribute('open');
    show.mockRestore();
  });
  it('announces confirmation as a modal and focuses the acknowledgment action', () => {
    render(<OutcomeDialog open onDismiss={vi.fn()} onStartNew={vi.fn()} />);

    const dialog = screen.getByRole('dialog', { name: /idea submitted/i });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription(/your idea is saved/i);
    expect(screen.getByText('Submission confirmed.')).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByRole('button', { name: /start a new idea/i })).toHaveFocus();
  });

  it('dismisses on Escape and delegates acknowledgment only to Start a new idea', () => {
    const onDismiss = vi.fn();
    const onStartNew = vi.fn();
    const props = { onDismiss, onStartNew };
    const view = render(<OutcomeDialog open {...props} />);
    const dialog = screen.getByRole('dialog');

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onStartNew).not.toHaveBeenCalled();

    view.rerender(<OutcomeDialog open={false} {...props} />);
    view.rerender(<OutcomeDialog open {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onDismiss).toHaveBeenCalledTimes(2);
    view.rerender(<OutcomeDialog open={false} {...props} />);
    view.rerender(<OutcomeDialog open {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /start a new idea/i }));
    expect(onStartNew).toHaveBeenCalledTimes(1);
  });

  it('does not install global listeners or create owned nodes', () => {
    const { container, unmount } = render(
      <OutcomeDialog open onDismiss={vi.fn()} onStartNew={vi.fn()} />,
    );
    expect(container.querySelectorAll('dialog')).toHaveLength(1);
    unmount();
    expect(container.childElementCount).toBe(0);
  });

  it('ignores background clicks and reports a throwing close without resetting', () => {
    const onFailure = vi.fn();
    const onDismiss = vi.fn();
    const onStartNew = vi.fn();
    const view = render(<OutcomeDialog open onFailure={onFailure} onDismiss={onDismiss} onStartNew={onStartNew} />);
    const dialog = screen.getByRole('dialog');
    fireEvent.click(dialog);
    expect(dialog).toHaveAttribute('open');
    expect(onDismiss).not.toHaveBeenCalled();
    vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(() => { throw new Error('close failed'); });
    fireEvent(dialog, new Event('cancel', { cancelable: true }));
    expect(onFailure).toHaveBeenCalledOnce();
    expect(onDismiss).toHaveBeenCalledOnce();
    expect(onStartNew).not.toHaveBeenCalled();
    expect(dialog).not.toHaveAttribute('open');
    expect(() => view.unmount()).not.toThrow();
  });
});