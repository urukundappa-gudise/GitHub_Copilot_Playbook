import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OutcomeDialog } from '../components/OutcomeDialog';

describe('outcome dialog', () => {
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
});