import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { NotificationService } from '../services/notification.service';
import { BusinessService } from '../services/business.service';
import { Notification } from '../models/notification.model';

type FilterTab = 'all' | 'unread' | 'read';

@Component({
  selector: 'app-notification-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './notification-list.component.html',
  styleUrl: './notification-list.component.scss',
})
export class NotificationListComponent implements OnInit {
  notifications: Notification[] = [];
  total = 0;
  page = 1;
  readonly limit = 10;
  loading = false;
  activeTab: FilterTab = 'all';
  selectedBusinessId = '';

  constructor(
    private notificationService: NotificationService,
    private businessService: BusinessService,
    private router: Router,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.businessService.getSelectedBusinessId().subscribe(id => {
      this.selectedBusinessId = id;
      this.page = 1;
      this.loadNotifications();
    });
  }

  setTab(tab: FilterTab): void {
    this.activeTab = tab;
    this.page = 1;
    this.loadNotifications();
  }

  loadNotifications(): void {
    this.loading = true;
    const readFilter = this.activeTab === 'all' ? undefined
      : this.activeTab === 'unread' ? false : true;
    this.notificationService.getNotifications({
      businessId: this.selectedBusinessId || undefined,
      read: readFilter,
      page: this.page,
      limit: this.limit,
    }).subscribe(result => {
      this.notifications = result.notifications;
      this.total = result.total;
      this.loading = false;
      this.cdr.detectChanges();
    });
  }

  get unreadCount(): number {
    return this.notifications.filter(n => !n.is_read).length;
  }

  get totalPages(): number { return Math.ceil(this.total / this.limit); }
  get pageStart(): number { return (this.page - 1) * this.limit + 1; }
  get pageEnd(): number { return Math.min(this.page * this.limit, this.total); }

  prevPage(): void { if (this.page > 1) { this.page--; this.loadNotifications(); } }
  nextPage(): void { if (this.page < this.totalPages) { this.page++; this.loadNotifications(); } }

  markAllAsRead(): void {
    this.notificationService.markAllAsRead(this.selectedBusinessId).subscribe(() => {
      this.loadNotifications();
    });
  }

  markAsRead(n: Notification): void {
    if (!n.is_read) {
      this.notificationService.markAsRead(n.id).subscribe(() => {
        n.is_read = true;
        this.cdr.detectChanges();
      });
    }
    this.router.navigate(['/orders', n.order_id]);
  }

  notifIcon(type: string): string {
    const normalized = type.toLowerCase();
    if (normalized.includes('delivery')) return '📦';
    if (normalized.includes('delay')) return '⏰';
    if (normalized.includes('exception')) return '⚠️';
    if (normalized.includes('status')) return '🔄';
    if (normalized.includes('pick')) return '🚚';
    return '🔔';
  }

  formatRelative(dateStr: string): string {
    const now = new Date();
    const then = new Date(dateStr);
    const diffMs = now.getTime() - then.getTime();
    const diffH = Math.floor(diffMs / 3600000);
    const diffD = Math.floor(diffH / 24);
    if (diffH < 1) return 'just now';
    if (diffH < 24) return `${diffH}h ago`;
    return `${diffD}d ago`;
  }
}
