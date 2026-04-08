import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { NotificationListComponent } from './notification-list.component';
import { NotificationService } from '../services/notification.service';
import { BusinessService } from '../services/business.service';

describe('NotificationListComponent', () => {
  let fixture: ComponentFixture<NotificationListComponent>;
  let component: NotificationListComponent;
  let mockNotifService: {
    getNotifications: ReturnType<typeof vi.fn>;
    markAsRead: ReturnType<typeof vi.fn>;
    markAllAsRead: ReturnType<typeof vi.fn>;
  };
  let mockBusinessService: { getSelectedBusinessId: ReturnType<typeof vi.fn> };

  const mockNotifications = [
    { id: 'notif-001', order_id: 'ord-001', business_id: 'biz-001', type: 'delivery',
      message: 'Package delivered', is_read: false, created_at: '2026-04-05T14:32:00Z' },
    { id: 'notif-002', order_id: 'ord-002', business_id: 'biz-001', type: 'delay',
      message: 'Package delayed', is_read: true, created_at: '2026-04-07T06:00:00Z' },
    { id: 'notif-003', order_id: 'ord-003', business_id: 'biz-001', type: 'exception',
      message: 'Delivery exception', is_read: false, created_at: '2026-04-06T11:20:00Z' },
  ];

  beforeEach(async () => {
    mockNotifService = {
      getNotifications: vi.fn(),
      markAsRead: vi.fn(),
      markAllAsRead: vi.fn(),
    };
    mockBusinessService = {
      getSelectedBusinessId: vi.fn(),
    };

    mockBusinessService.getSelectedBusinessId.mockReturnValue(of(''));
    mockNotifService.getNotifications.mockReturnValue(of({ notifications: mockNotifications, total: 3 }));
    mockNotifService.markAsRead.mockReturnValue(of(undefined));
    mockNotifService.markAllAsRead.mockReturnValue(of(undefined));

    await TestBed.configureTestingModule({
      imports: [NotificationListComponent],
      providers: [
        provideRouter([]),
        { provide: NotificationService, useValue: mockNotifService },
        { provide: BusinessService, useValue: mockBusinessService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(NotificationListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load notifications on init', () => {
    expect(component.notifications.length).toBe(3);
    expect(component.total).toBe(3);
    expect(component.loading).toBe(false);
  });

  it('should render notification messages', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('Package delivered');
  });

  it('should count unread notifications correctly', () => {
    expect(component.unreadCount).toBe(2);
  });

  it('should filter to unread on setTab("unread")', () => {
    mockNotifService.getNotifications.mockReturnValue(of({ notifications: [mockNotifications[0]], total: 1 }));
    component.setTab('unread');
    expect(component.activeTab).toBe('unread');
    expect(mockNotifService.getNotifications).toHaveBeenCalledWith(
      expect.objectContaining({ read: false })
    );
  });

  it('should filter to read on setTab("read")', () => {
    mockNotifService.getNotifications.mockReturnValue(of({ notifications: [mockNotifications[1]], total: 1 }));
    component.setTab('read');
    expect(component.activeTab).toBe('read');
    expect(mockNotifService.getNotifications).toHaveBeenCalledWith(
      expect.objectContaining({ read: true })
    );
  });

  it('should reset page to 1 when tab changes', () => {
    component.page = 3;
    component.setTab('all');
    expect(component.page).toBe(1);
  });

  it('should call markAsRead and navigate on markAsRead()', () => {
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate');
    const unread = mockNotifications[0];
    component.markAsRead(unread);
    expect(mockNotifService.markAsRead).toHaveBeenCalledWith('notif-001');
    expect(router.navigate).toHaveBeenCalledWith(['/orders', 'ord-001']);
  });

  it('should not call markAsRead for already-read notifications', () => {
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate');
    const read = mockNotifications[1];
    component.markAsRead(read);
    expect(mockNotifService.markAsRead).not.toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalled();
  });

  it('should call markAllAsRead and reload', () => {
    component.markAllAsRead();
    expect(mockNotifService.markAllAsRead).toHaveBeenCalled();
    expect(mockNotifService.getNotifications).toHaveBeenCalled();
  });

  it('should return correct notifIcon for each type', () => {
    expect(component.notifIcon('delivery')).toBe('📦');
    expect(component.notifIcon('delay')).toBe('⏰');
    expect(component.notifIcon('exception')).toBe('⚠️');
    expect(component.notifIcon('status')).toBe('🔄');
    expect(component.notifIcon('pickup')).toBe('🚚');
    expect(component.notifIcon('unknown')).toBe('🔔');
  });

  it('should return "just now" for very recent dates', () => {
    const nowish = new Date(Date.now() - 30000).toISOString(); // 30 seconds ago
    expect(component.formatRelative(nowish)).toBe('just now');
  });

  it('should return hours ago for dates within 24h', () => {
    const hoursAgo = new Date(Date.now() - 3 * 3600000).toISOString();
    expect(component.formatRelative(hoursAgo)).toBe('3h ago');
  });

  it('should return days ago for older dates', () => {
    const daysAgo = new Date(Date.now() - 2 * 86400000).toISOString();
    expect(component.formatRelative(daysAgo)).toBe('2d ago');
  });

  it('should compute totalPages', () => {
    component.total = 25;
    expect(component.totalPages).toBe(3);
  });
});
