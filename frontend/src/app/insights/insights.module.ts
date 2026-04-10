import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Routes } from '@angular/router';
import { BaseChartDirective, provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { InsightsComponent } from './insights.component';

const routes: Routes = [
  { path: '', component: InsightsComponent }
];

@NgModule({
  declarations: [InsightsComponent],
  imports: [
    CommonModule,
    BaseChartDirective,
    RouterModule.forChild(routes),
  ],
  providers: [
    provideCharts(withDefaultRegisterables()),
  ]
})
export class InsightsModule {}
