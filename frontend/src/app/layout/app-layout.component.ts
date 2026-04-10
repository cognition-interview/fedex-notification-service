import { ChangeDetectorRef, Component, OnInit, HostListener, ElementRef } from '@angular/core';
import { Router } from '@angular/router';
import { BusinessService } from '../services/business.service';
import { NotificationService } from '../services/notification.service';
import { Business } from '../models/business.model';
import { Notification } from '../models/notification.model';

@Component({
  selector: 'app-layout',
  templateUrl: './app-layout.component.html',
  styleUrls: ['./app-layout.component.scss'],
})
export class AppLayoutComponent implements OnInit {
  businesses: Business[] = [];
  selectedBusinessId = '';
  unreadCount = 0;
  recentNotifications: Notification[] = [];
  bellOpen = false;

  constructor(
    private businessService: BusinessService,
    private notificationService: NotificationService,
    private router: Router,
    private el: ElementRef,
    private cdr: ChangeDetectorRef,
  ) {}

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.el.nativeElement.querySelector('.bell-wrap')?.contains(event.target)) {
      this.bellOpen = false;
    }
  }

  ngOnInit(): void {
    console.log('[AppLayoutComponent] ngOnInit');
    this.businessService.getBusinesses(1, 100).subscribe(result => {
      console.log('[AppLayoutComponent] businesses loaded', {
        count: result.businesses.length,
        at: new Date().toISOString(),
      });
      this.businesses = result.businesses;
      this.cdr.detectChanges();
    });

    this.businessService.getSelectedBusinessId().subscribe(id => {
      console.log('[AppLayoutComponent] selectedBusinessId emitted', { id, at: new Date().toISOString() });
      this.selectedBusinessId = id;
      this.loadNotificationData(id);
      this.cdr.detectChanges();
    });
  }

  private loadNotificationData(businessId: string): void {
    this.notificationService
      .getNotifications({ businessId: businessId || undefined, read: false, limit: 5 })
      .subscribe(result => {
        this.recentNotifications = result.notifications.slice(0, 5);
        this.unreadCount = result.total;
        this.cdr.detectChanges();
      });
  }

  onBusinessChange(id: string): void {
    console.log('[AppLayoutComponent] onBusinessChange', { id, at: new Date().toISOString() });
    this.businessService.setSelectedBusinessId(id);
  }

  toggleBell(): void {
    this.bellOpen = !this.bellOpen;
  }

  closeBell(): void {
    this.bellOpen = false;
  }

  goToOrder(orderId: string): void {
    this.bellOpen = false;
    this.router.navigate(['/orders', orderId]);
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

  notifIcon(type: string): string {
    const icons: Record<string, string> = {
      delivery: '📦',
      delay: '⏰',
      exception: '⚠️',
      status: '🔄',
      pickup: '🚚',
    };
    return icons[type] ?? '🔔';
  }
}
