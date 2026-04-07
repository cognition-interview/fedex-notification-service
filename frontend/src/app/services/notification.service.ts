import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map, shareReplay, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { Notification } from '../models/notification.model';

export interface NotificationFilters {
  businessId?: string;
  read?: boolean;
  page?: number;
  limit?: number;
}

export interface PaginatedNotifications {
  notifications: Notification[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private notificationsCache = new Map<string, Observable<PaginatedNotifications>>();

  constructor(private http: HttpClient) {}

  getNotifications(filters?: NotificationFilters): Observable<PaginatedNotifications> {
    const key = JSON.stringify(filters ?? {});
    const cached = this.notificationsCache.get(key);
    if (cached) return cached;

    let params = new HttpParams();
    if (filters?.businessId) params = params.set('businessId', filters.businessId);
    if (filters?.read !== undefined) params = params.set('read', filters.read.toString());
    if (filters?.page) params = params.set('page', filters.page.toString());
    if (filters?.limit) params = params.set('limit', filters.limit.toString());

    const request$ = this.http
      .get<PaginatedNotifications>(`${environment.apiUrl}/api/notifications`, { params })
      .pipe(
        map(result => ({
          notifications: result.notifications.map(n => ({
            ...n,
            is_read: this.toBoolean(n.is_read),
          })),
          total: Number(result.total) || 0,
        })),
        catchError(() => of({ notifications: [], total: 0 })),
        shareReplay(1),
      );

    this.notificationsCache.set(key, request$);
    return request$;
  }

  markAsRead(id: string): Observable<void> {
    return this.http
      .patch<void>(`${environment.apiUrl}/api/notifications/${id}/read`, {})
      .pipe(tap(() => this.notificationsCache.clear()));
  }

  markAllAsRead(businessId?: string): Observable<void> {
    const body = businessId ? { businessId } : {};
    return this.http
      .patch<void>(`${environment.apiUrl}/api/notifications/read-all`, body)
      .pipe(tap(() => this.notificationsCache.clear()));
  }

  getUnreadCount(businessId?: string): Observable<number> {
    return this.getNotifications({ businessId, read: false, limit: 100 }).pipe(
      map(result => result.total)
    );
  }

  private toBoolean(value: unknown): boolean {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      return normalized === 'true' || normalized === 't' || normalized === '1';
    }
    if (typeof value === 'number') return value !== 0;
    return false;
  }
}
